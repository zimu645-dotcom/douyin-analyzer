# -*- coding: utf-8 -*-
"""飞书多维表格 API 客户端
功能：获取 access_token、批量写入记录
API文档：https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create
"""
import json
import time
import urllib.request
import urllib.error


class FeishuClient:
    """飞书多维表格客户端"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_token = None
        self.token_expire = 0

    def _request(self, method, url, data=None, headers=None):
        """发送HTTP请求"""
        # 清除代理（防止环境变量干扰）
        import os
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(k, None)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        if headers is None:
            headers = {}
        headers["Content-Type"] = "application/json; charset=utf-8"

        req_data = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

        try:
            with opener.open(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"飞书API错误 ({e.code}): {error_body}")

    def _request_raw(self, method, url, data_bytes, headers):
        """发送二进制/表单请求（文件上传用），headers 需含 Content-Type"""
        import os
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(k, None)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        try:
            with opener.open(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"飞书API错误 ({e.code}): {error_body}")

    def upload_file(self, file_path, app_token):
        """上传文件到飞书云空间（多维表格附件），返回 file_token"""
        import os as _os
        import uuid as _uuid
        url = f"{self.BASE_URL}/drive/v1/medias/upload_all"
        file_name = _os.path.basename(file_path)
        with open(file_path, "rb") as f:
            file_data = f.read()
        boundary = _uuid.uuid4().hex
        body = []
        for k, v in [("file_name", file_name), ("parent_type", "bitable_file"),
                     ("parent_node", app_token), ("size", str(len(file_data))), ("extra", "")]:
            body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
                    f'Content-Type: application/octet-stream\r\n\r\n'.encode())
        body.append(file_data)
        body.append(f'\r\n--{boundary}--\r\n'.encode())
        headers = self._auth_headers()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        result = self._request_raw("POST", url, b"".join(body), headers)
        if result.get("code") != 0:
            raise RuntimeError(f"上传文件失败: {result.get('msg', '未知错误')}")
        return result.get("data", {}).get("file_token")

    def get_tenant_token(self):
        """获取 tenant_access_token（自动缓存，过期前刷新）"""
        if self.tenant_token and time.time() < self.token_expire - 60:
            return self.tenant_token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }
        result = self._request("POST", url, data)

        if result.get("code") != 0:
            raise RuntimeError(f"获取token失败: {result.get('msg', '未知错误')}")

        self.tenant_token = result["tenant_access_token"]
        self.token_expire = time.time() + result.get("expire", 7200)
        return self.tenant_token

    def _auth_headers(self):
        """带认证的请求头"""
        token = self.get_tenant_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def batch_create_records(self, app_token, table_id, records):
        """批量创建记录（单次最多500条）

        Args:
            app_token: 多维表格的 app_token
            table_id: 数据表的 table_id
            records: 记录列表，每条格式: {"fields": {"字段名": "值", ...}}

        Returns:
            创建结果 dict
        """
        app_token = (app_token or "").strip()
        table_id = (table_id or "").strip()
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"

        # 飞书单次最多500条，分批处理
        batch_size = 500
        all_results = []

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            data = {"records": batch}
            result = self._request("POST", url, data, self._auth_headers())

            if result.get("code") != 0:
                raise RuntimeError(f"写入记录失败: {result.get('msg', '未知错误')}")

            all_results.append(result)

            # 避免频率限制
            if i + batch_size < len(records):
                time.sleep(0.5)

        return {
            "total": len(records),
            "batches": len(all_results),
        }

    def update_record(self, app_token, table_id, record_id, fields):
        """更新单条记录

        Args:
            app_token: 多维表格的 app_token
            table_id: 数据表的 table_id
            record_id: 记录ID
            fields: 要更新的字段 {"字段名": "新值", ...}
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        data = {"fields": fields}
        result = self._request("PUT", url, data, self._auth_headers())

        if result.get("code") != 0:
            raise RuntimeError(f"更新记录失败: {result.get('msg', '未知错误')}")
        return result

    def list_records(self, app_token, table_id, filter_str=None, page_size=100):
        """查询记录列表

        Args:
            app_token: 多维表格的 app_token
            table_id: 数据表的 table_id
            filter_str: 过滤条件（可选）
            page_size: 每页数量（默认100）

        Returns:
            记录列表
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        params = {"page_size": page_size}
        if filter_str:
            params["filter"] = filter_str

        # 构建查询URL
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query_string}"

        result = self._request("GET", full_url, headers=self._auth_headers())

        if result.get("code") != 0:
            raise RuntimeError(f"查询记录失败: {result.get('msg', '未知错误')}")
        return result.get("data", {}).get("items", [])

    def list_fields(self, app_token, table_id):
        """获取表格字段列表

        Args:
            app_token: 多维表格的 app_token
            table_id: 数据表的 table_id

        Returns:
            字段列表
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        result = self._request("GET", url, headers=self._auth_headers())

        if result.get("code") != 0:
            raise RuntimeError(f"获取字段失败: {result.get('msg', '未知错误')}")
        return result.get("data", {}).get("items", [])

    def create_field(self, app_token, table_id, field_name, field_type=1):
        """创建表格字段

        Args:
            app_token: 多维表格的 app_token
            table_id: 数据表的 table_id
            field_name: 字段名称
            field_type: 字段类型（1=文本, 2=数字, 5=日期 等）

        Returns:
            创建结果
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        data = {
            "field_name": field_name,
            "type": field_type,
        }
        # 链接类型需要额外配置
        if field_type == 15:
            data["property"] = {"options": []}

        result = self._request("POST", url, data, self._auth_headers())

        if result.get("code") != 0:
            # 字段已存在不算错误
            if "FieldNameExist" in str(result.get("msg", "")):
                return {"ok": True, "message": "字段已存在"}
            raise RuntimeError(f"创建字段失败: {result.get('msg', '未知错误')}")
        return result

    def test_connection(self):
        """测试连接是否正常"""
        try:
            self.get_tenant_token()
            return {"ok": True, "message": "连接成功"}
        except Exception as e:
            return {"ok": False, "message": str(e)}
