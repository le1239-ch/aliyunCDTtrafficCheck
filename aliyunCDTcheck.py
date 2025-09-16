import os
import json
from datetime import datetime
from alibabacloud_cdt20210813.client import Client as CDTClient
from alibabacloud_cdt20210813.models import ListCdtInternetTrafficRequest
from alibabacloud_tea_openapi.models import Config as OpenAPIConfig
import aiohttp
import asyncio

# 配置参数（从环境变量或配置文件读取）
_access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
_access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
_max_traffic_gb = int(os.getenv("MAX_TRAFFIC_GB", "20"))  # 流量阈值（GB）
_feishu_webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "")  # 飞书机器人webhook地址

def load_config():
    """加载配置文件（可选）"""
    global _access_key_id, _access_key_secret, _max_traffic_gb, _feishu_webhook_url
    try:
        with open('aliyunCDTconfig.json', 'r') as f:
            config = json.load(f)
            _access_key_id = config.get("access_key_id", _access_key_id)
            _access_key_secret = config.get("access_key_secret", _access_key_secret)
            _max_traffic_gb = int(config.get("max_traffic_gb", _max_traffic_gb))
            _feishu_webhook_url = config.get("feishu_webhook_url", _feishu_webhook_url)
    except FileNotFoundError:
        pass
    
def write_log(message):
    """打印日志"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

async def get_traffic_gb():
    """获取当前流量（单位：GB）"""
    config = OpenAPIConfig(
        access_key_id=_access_key_id,
        access_key_secret=_access_key_secret,
        endpoint="cdt.aliyuncs.com"
    )
    client = CDTClient(config)
    request = ListCdtInternetTrafficRequest()

    try:
        response = await client.list_cdt_internet_traffic_async(request)
        if response.status_code == 200:
            total_bytes = sum(
                item.traffic for item in response.body.traffic_details 
                if item.traffic is not None
            )
            return total_bytes / (1024 ** 3)  # 转换为GB
    except Exception as e:
        write_log(f"获取流量失败: {str(e)}")
    return 0

async def check_traffic():
    """检测流量并发送通知"""
    traffic_gb = await get_traffic_gb()
    write_log(f"当前流量: {traffic_gb:.4f} GB / 阈值: {_max_traffic_gb} GB")
    
    if traffic_gb > _max_traffic_gb:
        write_log("⚠️ 流量已超限！")
        # 发送超限告警
        await send_feishu_alert(traffic_gb, _max_traffic_gb, is_exceeded=True)
        return False
    else:
        write_log("✅ 流量正常")
        # 发送正常通知
        await send_feishu_alert(traffic_gb, _max_traffic_gb, is_exceeded=False)
        return True

async def send_feishu_alert(traffic_gb, max_traffic_gb, is_exceeded=False):
    """发送飞书机器人通知"""
    if not _feishu_webhook_url:
        write_log("飞书webhook地址未配置，无法发送通知")
        return False
    
    try:
        # 根据是否超限构建不同的消息内容
        if is_exceeded:
            title = "🚨 流量超限告警"
            template = "red"
            status_text = "❌ 流量已超过设定阈值，请及时处理！"
        else:
            title = "✅ 流量正常通知"
            template = "green"
            status_text = "✅ 流量使用正常，未超过阈值"
        
        # 构建飞书消息内容
        message = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**阿里云CDT流量监控**\n\n当前流量: {traffic_gb:.3f} GB\n阈值限制: {max_traffic_gb} GB\n使用率: {(traffic_gb/max_traffic_gb)*100:.1f}%\n\n{status_text}"
                        }
                    },
                ],
                "header": {
                    "template": template,
                    "title": {
                        "content": title,
                        "tag": "plain_text"
                    }
                }
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(_feishu_webhook_url, json=message) as response:
                if response.status == 200:
                    write_log("飞书通知发送成功")
                    return True
                else:
                    write_log(f"飞书通知发送失败: {response.status}")
                    return False
                    
    except Exception as e:
        write_log(f"发送飞书通知时出错: {str(e)}")
        return False


async def main():
    load_config()
    await check_traffic()

if __name__ == "__main__":
    asyncio.run(main())
