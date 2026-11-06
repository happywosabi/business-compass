"""有时间与UUID的稳定游标，不在游标中传业务查询。"""

import base64
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import tuple_


def cursor_for(date, identity):
    return base64.urlsafe_b64encode(f"{date.isoformat()}|{identity}".encode()).decode()


def before(query, date_column, id_column, cursor):
    if not cursor:
        return query
    try:
        date, identity = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        stamp = datetime.fromisoformat(date)
        if stamp.tzinfo is None:
            raise ValueError()
        return query.where(tuple_(date_column, id_column) < (stamp, UUID(identity)))
    except (ValueError, TypeError, UnicodeError) as error:
        raise HTTPException(422, "无效的分页游标") from error
