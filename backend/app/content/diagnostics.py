"""管理界面只展示固定诊断代码，禁止回传上游正文、URL、凭据和异常文本。"""

SOURCE_NAMES = {
    "chinanews_life": "中新网·生活",
    "chinanews_finance": "中新网·财经",
    "chinanews_latest": "中新网·即时",
    "foodmate": "食品伙伴网",
    "dailyhot": "可选热点聚合源",
}
SOURCE_STATUSES = {
    "ok": "读取成功",
    "redirect": "来源返回重定向，已拒绝跟随",
    "http_error": "来源 HTTP 请求失败",
    "timeout": "读取超时",
    "network_error": "网络连接失败",
    "format_error": "内容不是有效 RSS/JSON",
    "oversized": "响应超过大小限制",
    "encoding_error": "来源未提供受支持的传输编码",
}
STAGES = {
    "sources": "读取来源",
    "classification": "模型筛选",
    "embedding": "向量去重",
    "publishing": "保存候选",
    "completed": "已完成",
}


def public_diagnostics(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {}
    output = {}
    if isinstance(value.get("stage"), str) and value["stage"] in STAGES:
        output["stage"] = value["stage"]
    for key in ("candidates", "approved", "added"):
        if type(value.get(key)) is int and 0 <= value[key] <= 10000:
            output[key] = value[key]
    if value.get("embedding_fallback") is True:
        output["embedding_fallback"] = True
    output["sources"] = []
    sources = value.get("sources", [])
    for source in sources[:12] if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            continue
        if (
            not isinstance(source.get("source"), str)
            or not isinstance(source.get("status"), str)
            or source["source"] not in SOURCE_NAMES
            or source["status"] not in SOURCE_STATUSES
        ):
            continue
        row = {key: source[key] for key in ("source", "status")}
        for key, low, high in (("http_status", 100, 599), ("items", 0, 10000)):
            if type(source.get(key)) is int and low <= source[key] <= high:
                row[key] = source[key]
        output["sources"].append(row)
    return output


def collection_error(row) -> str | None:
    if not row.error:
        return None
    diagnostics = public_diagnostics(row.diagnostics)
    stage = diagnostics.get("stage")
    if stage == "sources":
        return "资讯来源读取失败；尚未调用模型，请查看来源状态"
    if stage == "classification":
        return "模型筛选失败，请检查模型服务或返回格式"
    if stage == "embedding":
        return "向量处理失败，请检查向量服务配置"
    if stage == "publishing":
        return "候选保存失败，请检查数据库状态"
    return "采集未完成，旧记录未保存具体阶段；请查看服务日志"
