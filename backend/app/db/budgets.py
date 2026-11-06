"""业务行JSONB的UTF-8大小账本；触发器与业务写入共享事务。"""

from sqlalchemy import text

OWNERS = {
    "profiles": "NEW.user_id",
    "ai_runs": "NEW.user_id",
    "parameter_changes": "(SELECT user_id FROM profiles WHERE id = NEW.profile_id)",
    "evaluations": "(SELECT user_id FROM profiles WHERE id = NEW.profile_id)",
    "conversations": "(SELECT user_id FROM profiles WHERE id = NEW.profile_id)",
    "content_drafts": "(SELECT user_id FROM profiles WHERE id = NEW.profile_id)",
    "messages": "(SELECT user_id FROM ai_runs WHERE id = NEW.run_id)",
    "evaluation_reports": "(SELECT p.user_id FROM evaluations e JOIN profiles p ON p.id = e.profile_id WHERE e.id = NEW.evaluation_id)",
    "pending_actions": "NEW.user_id",
}


def statements(*, backfill=False):
    yield """CREATE OR REPLACE FUNCTION compass_storage() RETURNS trigger AS $$
    DECLARE owner_id uuid; prior_size int := 0; new_size int := 0;
        delta_count int := 0; usage_row resource_usage%ROWTYPE; verified bool;
    BEGIN
        IF TG_OP = 'DELETE' THEN
            SELECT user_id, size INTO owner_id, prior_size FROM storage_entries
              WHERE table_name = TG_TABLE_NAME AND row_id = OLD.id;
            IF owner_id IS NOT NULL THEN
                UPDATE resource_usage SET storage_bytes = GREATEST(0, storage_bytes-prior_size),
                  profile_count = GREATEST(0, profile_count-CASE WHEN TG_TABLE_NAME='profiles' THEN 1 ELSE 0 END)
                  WHERE user_id=owner_id;
                DELETE FROM storage_entries WHERE table_name=TG_TABLE_NAME AND row_id=OLD.id;
            END IF;
            RETURN OLD;
        END IF;
        EXECUTE TG_ARGV[0] INTO owner_id USING NEW;
        IF owner_id IS NULL THEN RETURN NEW; END IF;
        INSERT INTO resource_usage(user_id) VALUES(owner_id) ON CONFLICT DO NOTHING;
        SELECT * INTO usage_row FROM resource_usage WHERE user_id=owner_id FOR UPDATE;
        SELECT email_verified_at IS NOT NULL INTO verified FROM users WHERE id=owner_id;
        SELECT size INTO prior_size FROM storage_entries WHERE table_name=TG_TABLE_NAME AND row_id=NEW.id;
        prior_size := COALESCE(prior_size,0);
        new_size := octet_length(to_jsonb(NEW)::text);
        IF TG_TABLE_NAME='profiles' AND new_size>262144 AND new_size>prior_size
          AND NOT (TG_OP='UPDATE' AND to_jsonb(NEW)->>'deleted_at' IS NOT NULL AND to_jsonb(OLD)->>'deleted_at' IS NULL) THEN
            RAISE EXCEPTION 'compass_document_limit' USING ERRCODE='P0001';
        END IF;
        IF TG_OP='INSERT' AND TG_TABLE_NAME='profiles' THEN delta_count:=1; END IF;
        IF delta_count>0 AND usage_row.profile_count+delta_count > (CASE WHEN verified THEN 100 ELSE 10 END) THEN
            RAISE EXCEPTION 'compass_profile_limit' USING ERRCODE='P0001';
        END IF;
        IF new_size>prior_size AND usage_row.storage_bytes+new_size-prior_size > (CASE WHEN verified THEN 104857600 ELSE 10485760 END)
          AND NOT (TG_TABLE_NAME='profiles' AND TG_OP='UPDATE' AND to_jsonb(NEW)->>'deleted_at' IS NOT NULL AND to_jsonb(OLD)->>'deleted_at' IS NULL) THEN
            RAISE EXCEPTION 'compass_storage_limit' USING ERRCODE='P0001';
        END IF;
        UPDATE resource_usage SET storage_bytes=storage_bytes+new_size-prior_size,
          profile_count=profile_count+delta_count WHERE user_id=owner_id;
        INSERT INTO storage_entries(table_name,row_id,user_id,size) VALUES(TG_TABLE_NAME,NEW.id,owner_id,new_size)
          ON CONFLICT(table_name,row_id) DO UPDATE SET size=EXCLUDED.size;
        RETURN NEW;
    END; $$ LANGUAGE plpgsql"""
    for table, owner in OWNERS.items():
        # 参数化动态SQL只使用固定表名/列名，不接受用户输入。
        query = "SELECT " + owner.replace("NEW.", "($1).")
        yield f"DROP TRIGGER IF EXISTS compass_budget ON {table}"
        yield f"CREATE TRIGGER compass_budget AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION compass_storage('{query}')"
    if backfill:
        for table, owner in OWNERS.items():
            yield f"INSERT INTO storage_entries(table_name,row_id,user_id,size) SELECT '{table}', n.id, {owner.replace('NEW.', 'n.')}, octet_length(to_jsonb(n)::text) FROM {table} n ON CONFLICT DO NOTHING"
        yield """INSERT INTO resource_usage(user_id,storage_bytes,profile_count)
            SELECT u.id, COALESCE(sum(s.size),0), count(*) FILTER(WHERE s.table_name='profiles')
            FROM users u LEFT JOIN storage_entries s ON s.user_id=u.id GROUP BY u.id
            ON CONFLICT(user_id) DO UPDATE SET storage_bytes=EXCLUDED.storage_bytes,profile_count=EXCLUDED.profile_count"""


async def install(connection):
    for statement in statements():
        await connection.execute(text(statement))


async def lock_usage(db, user_id):
    """写入统一先锁账号账本，再锁档案，避免跨子系统倒序死锁。"""
    await db.execute(
        text("INSERT INTO resource_usage(user_id) VALUES (:uid) ON CONFLICT DO NOTHING"),
        {"uid": user_id},
    )
    await db.execute(
        text("SELECT user_id FROM resource_usage WHERE user_id=:uid FOR UPDATE"), {"uid": user_id}
    )
