import requests
import os
from wxmsg import send_wx

# -----------------------------
# 配置账号（优先使用环境变量）
# -----------------------------
USERNAME = os.getenv("TEXO_USER") or "378600950@qq.com"
PASSWORD = os.getenv("TEXO_PASS") or "cattle3213505"

# -----------------------------
# 订阅续费配置
# -----------------------------
PLAN_ID = "3"              # 订阅 plan_id
PERIOD = "onetime_price"   # 可选: "onetime_price"
LOW_THRESHOLD = 2 * (1 << 30)  # 当剩余流量低于 2GB 时续费

ORDER_SAVE_URL = "https://xboard.texo.network/api/v1/user/order/save"
ORDER_CHECKOUT_URL = "https://xboard.texo.network/api/v1/user/order/checkout"

# -----------------------------
# 企业微信配置（环境变量）
# -----------------------------
WX_CORPID = os.getenv("WX_CORPID")
WX_CORPSECRET = os.getenv("WX_CORPSECRET")
WX_AGENTID = os.getenv("WX_AGENTID")

# -----------------------------
# 微信通知封装
# -----------------------------
def notify(msg):
    print(msg)
    if WX_CORPID and WX_CORPSECRET and WX_AGENTID:
        send_wx(msg, WX_CORPID, WX_CORPSECRET, WX_AGENTID)

# -----------------------------
# 登录接口
# -----------------------------
login_url = "https://xboard.texo.network/api/v1/passport/auth/login"
login_data = {"email": USERNAME, "password": PASSWORD}
headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"}

try:
    resp = requests.post(login_url, data=login_data, headers=headers, timeout=10)
    resp.raise_for_status()
except requests.RequestException as e:
    notify(f"请求失败: {e}")
    raise SystemExit()

result = resp.json()
if result.get("status") != "success" or "data" not in result:
    notify(f"登录失败: {result.get('message')}")
    raise SystemExit()

data = result["data"]
auth_data = data.get("auth_data")
if not auth_data:
    notify("未获取到 auth_data")
    raise SystemExit()

notify("登录成功，auth_data 已获取")

# -----------------------------
# 获取订阅/流量信息
# -----------------------------
subscribe_url = "https://xboard.texo.network/api/v1/user/getSubscribe"
params = {"sid": data["token"]}
headers_auth = {"Authorization": auth_data}

try:
    resp = requests.get(subscribe_url, headers=headers_auth, params=params, timeout=10)
    resp.raise_for_status()
except requests.RequestException as e:
    notify(f"获取流量信息失败: {e}")
    raise SystemExit()

sub_result = resp.json()
if sub_result.get("status") != "success" or "data" not in sub_result:
    notify(f"获取流量信息失败: {sub_result.get('message')}")
    raise SystemExit()

sub_data = sub_result["data"]

# -----------------------------
# 解析流量
# -----------------------------
u = sub_data.get("u", 0)
d = sub_data.get("d", 0)
total = sub_data.get("transfer_enable", 0)
used = u + d
remaining = total - used

def bytes_to_readable(b):
    if b >= 1 << 30:
        return f"{b / (1<<30):.2f} GB"
    elif b >= 1 << 20:
        return f"{b / (1<<20):.2f} MB"
    elif b >= 1 << 10:
        return f"{b / (1<<10):.2f} KB"
    return f"{b} B"

# 构造流量信息消息
flow_msg = (
    f"===== 流量信息 =====\n"
    f"已上传: {bytes_to_readable(u)}\n"
    f"已下载: {bytes_to_readable(d)}\n"
    f"总已用: {bytes_to_readable(used)}\n"
    f"总流量: {bytes_to_readable(total)}\n"
    f"剩余流量: {bytes_to_readable(remaining)}\n"
    f"订阅链接: {sub_data.get('subscribe_url')}"
)
notify(flow_msg)

# -----------------------------
# 自动创建订单 + 支付
# -----------------------------
def create_order(token, plan_id, period):
    headers_order = {
        "accept": "application/json, text/plain, */*",
        "authorization": token,
        "content-type": "application/x-www-form-urlencoded",
    }
    data_order = {"plan_id": plan_id, "period": period}
    try:
        resp = requests.post(ORDER_SAVE_URL, headers=headers_order, data=data_order)
        resp.raise_for_status()
        res_json = resp.json()
        trade_no = res_json.get("data")
        if trade_no:
            notify(f"订单创建成功，trade_no: {trade_no}")
            return trade_no
        else:
            notify(f"订单创建失败: {resp.text}")
            return None
    except requests.RequestException as e:
        notify(f"订单创建请求异常: {e}")
        return None

def pay_order(token, trade_no):
    if not trade_no:
        notify("无可支付订单")
        return False
    headers_pay = {
        "accept": "application/json, text/plain, */*",
        "authorization": token,
        "content-type": "application/x-www-form-urlencoded",
    }
    data_pay = {"trade_no": trade_no, "method": "1"}  # 默认支付方式
    try:
        resp = requests.post(ORDER_CHECKOUT_URL, headers=headers_pay, data=data_pay)
        try:
            res_json = resp.json()
        except Exception:
            notify(f"支付接口返回非 JSON: {resp.text}")
            return False
        if res_json.get("status") == "success" or res_json.get("data") is True:
            notify(f"订单 {trade_no} 支付成功")
            return True
        else:
            notify(f"订单 {trade_no} 支付接口返回异常或已支付: {resp.text}")
            return False
    except requests.RequestException as e:
        notify(f"支付请求异常: {e}")
        return False

# -----------------------------
# 判断流量是否低于阈值，自动续费
# -----------------------------
if remaining < LOW_THRESHOLD:
    notify(f"流量低于阈值，开始自动续费流程...\n剩余流量: {bytes_to_readable(remaining)}")
    trade_no = create_order(auth_data, PLAN_ID, PERIOD)
    if trade_no:
        pay_order(auth_data, trade_no)
    else:
        notify("自动续费失败：订单创建失败")
else:
    notify(f"流量充足，无需续费\n剩余流量: {bytes_to_readable(remaining)}")
