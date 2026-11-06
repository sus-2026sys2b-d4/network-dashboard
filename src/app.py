import re
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# トポロジ図に基づく完全な機器データベース
TOPOLOGY = {
    "192.168.10.1":   {"name": "PC0", "vlan": 10, "site": "Left", "type": "PC"},
    "192.168.10.2":   {"name": "PC2", "vlan": 10, "site": "Left", "type": "PC"},
    "192.168.10.254": {"name": "R1_VLAN10_GW", "vlan": 10, "site": "Left", "type": "GW"},
    "192.168.20.1":   {"name": "PC1", "vlan": 20, "site": "Left", "type": "PC"},
    "192.168.20.2":   {"name": "PC3", "vlan": 20, "site": "Left", "type": "PC"},
    "192.168.20.254": {"name": "R1_VLAN20_GW", "vlan": 20, "site": "Left", "type": "GW"},
    "192.168.100.1":  {"name": "Router1", "vlan": None, "site": "Left", "type": "Router"},
    "192.168.30.1":   {"name": "PC4", "vlan": 30, "site": "Right", "type": "PC"},
    "192.168.30.2":   {"name": "PC6", "vlan": 30, "site": "Right", "type": "PC"},
    "192.168.30.254": {"name": "R2_VLAN30_GW", "vlan": 30, "site": "Right", "type": "GW"},
    "192.168.40.1":   {"name": "PC5", "vlan": 40, "site": "Right", "type": "PC"},
    "192.168.40.2":   {"name": "PC7", "vlan": 40, "site": "Right", "type": "PC"},
    "192.168.40.254": {"name": "R2_VLAN40_GW", "vlan": 40, "site": "Right", "type": "GW"},
    "192.168.100.2":  {"name": "Router2", "vlan": None, "site": "Right", "type": "Router"},
}

# 履歴管理用リスト（個別に削除できるようIDを持たせます）
dashboard_records = []
record_id_counter = 0

# マトリクス（総当たり）状態管理用辞書
matrix_status = {}

def init_matrix():
    """マトリクス表の初期化"""
    pc_names = [info["name"] for info in TOPOLOGY.values() if info["type"] == "PC"]
    pc_names.sort() 
    for src in pc_names:
        matrix_status[src] = {}
        for dst in pc_names:
            if src == dst:
                matrix_status[src][dst] = "-" 
            else:
                matrix_status[src][dst] = "UNKNOWN"

def recalculate_matrix():
    """蓄積された履歴データからマトリクス表を最初から再計算する（削除時の巻き戻し用）"""
    init_matrix()
    # 過去の履歴を「古い順（追加された順）」に読み直してマトリクスを上書きしていく
    for record in dashboard_records:
        src_name = record["src_info"]
        dst_name = record["dst_info"]
        # 送信元と宛先がどちらもPCとしてトポロジ内に実在する場合のみ反映
        if src_name in matrix_status and dst_name in matrix_status[src_name]:
            matrix_status[src_name][dst_name] = record["status"]

init_matrix()

def analyze_log(log_text, src_ip):
    global record_id_counter
    result = {
        "id": record_id_counter,
        "command_type": "Unknown",
        "status": "Unknown",
        "src_info": "未指定",
        "dst_info": "なし",
        "comm_type": "判定不可",
        "summary": "ログを解析できませんでした",
        "layer_issue": "なし (正常)",
    }
    record_id_counter += 1
    
    if not log_text.strip():
        return result

    src_node = TOPOLOGY.get(src_ip)
    if src_node:
        result["src_info"] = src_node["name"]
    else:
        return result

    # --- 1. SHOW IP ROUTEの解析 ---
    if "show ip route" in log_text.lower() or "codes:" in log_text.lower():
        result["command_type"] = "show ip route"
        result["status"] = "INFO"
        result["comm_type"] = "経路確認"
        result["dst_info"] = "ルータ内部"
        
        protocols = []
        if re.search(r'^R\s', log_text, re.MULTILINE): protocols.append("RIP (AD:120)")
        if re.search(r'^O\s', log_text, re.MULTILINE): protocols.append("OSPF (AD:110)")
        if re.search(r'^B\s', log_text, re.MULTILINE): protocols.append("BGP (AD:20)")
        
        if protocols:
            result["summary"] = f"稼働プロトコル: " + " / ".join(protocols)
        else:
            result["summary"] = "直結(C)・静的(S)のみ（ルーティング未学習）"
        return result

    # --- 2. PINGの解析 ---
    elif "ping" in log_text.lower() or "reply from" in log_text.lower() or "sending" in log_text.lower() or "からの応答" in log_text:
        result["command_type"] = "ping"
        
        dst_match = re.search(r"(?:pinging|ping|to|^|\s)([0-9\.]{7,15})", log_text, re.IGNORECASE)
        if "に ping を送信" in log_text:
            dst_match = re.search(r"([0-9\.]{7,15})\s+に\s*ping", log_text)
        dst_ip = dst_match.group(1) if dst_match else None

        dst_node = None
        if dst_ip:
            dst_node = TOPOLOGY.get(dst_ip)
            if dst_node:
                result["dst_info"] = dst_node["name"]
            else:
                result["dst_info"] = f"トポロジ外 ({dst_ip})"

        if "unreachable" in log_text.lower() or "uuuuu" in log_text.lower() or "宛先ホストに到達できません" in log_text:
            result["status"] = "NG"
            result["layer_issue"] = "L3 (ルーティング不在)"
            result["summary"] = "デフォルトゲートウェイまで届いていますが、その先の経路がありません"
        elif "100% loss" in log_text or "100% の損失" in log_text or "....." in log_text or "要求がタイムアウトしました" in log_text:
            result["status"] = "NG"
            result["summary"] = "相手からの応答が一切ありません（物理断、VLANミス、またはFW遮断）"
            result["layer_issue"] = "L1/L2 (物理・VLAN) または L3 (戻り経路なし)"
        elif "timed out" in log_text.lower() or "損失" in log_text and not "0%" in log_text:
            result["status"] = "NG"
            result["summary"] = "一部のパケットが損失しました（ARP解決遅延、またはネットワークの不安定）"
            result["layer_issue"] = "L2 (ARP未解決などによる初回ドロップの可能性)"
        elif "!!!!!" in log_text or ("reply from" in log_text.lower() and "bytes=" in log_text.lower()) or ("からの応答" in log_text and "バイト" in log_text and not "宛先ホスト" in log_text):
            result["status"] = "OK"
            result["summary"] = "正常に通信が完了しました (100%到達)"
            result["layer_issue"] = "なし (正常)"

        if dst_node:
            if src_node["site"] != dst_node["site"]: result["comm_type"] = "遠隔サイト通信"
            elif src_node.get("vlan") != dst_node.get("vlan"): result["comm_type"] = "異なるVLAN間通信"
            else: result["comm_type"] = "同一VLAN間通信"
        else:
            result["comm_type"] = "トポロジ外への通信"

    # --- 3. TRACERT / TRACEROUTEの解析 ---
    elif "tracing" in log_text.lower() or "traceroute" in log_text.lower() or "ルートをトレースしています" in log_text:
        result["command_type"] = "tracert"
        
        dst_match = re.search(r"(?:tracing route to|traceroute to|^|\s)([0-9\.]{7,15})", log_text, re.IGNORECASE)
        if "へのルートをトレース" in log_text:
            dst_match = re.search(r"([0-9\.]{7,15})\s+へのルートをトレース", log_text)
        dst_ip = dst_match.group(1) if dst_match else None
        
        dst_node = TOPOLOGY.get(dst_ip) if dst_ip else None
        if dst_node:
            result["dst_info"] = dst_node["name"]
            if src_node["site"] != dst_node["site"]: result["comm_type"] = "遠隔サイト通信"
            elif src_node.get("vlan") != dst_node.get("vlan"): result["comm_type"] = "異なるVLAN間通信"
            else: result["comm_type"] = "同一VLAN間通信"
        else:
            if dst_ip:
                result["dst_info"] = f"トポロジ外 ({dst_ip})"
                result["comm_type"] = "トポロジ外への通信"

        route_path = [src_node["name"]]
        has_error_message = "到達できません" in log_text or "unreachable" in log_text.lower()

        for line in log_text.split('\n'):
            if re.search(r'^\s*\d+\s+', line):
                ip_match = re.search(r'([0-9\.]{7,15})', line)
                if ip_match:
                    hop_ip = ip_match.group(1)
                    if hop_ip in TOPOLOGY:
                        if TOPOLOGY[hop_ip]["name"] != route_path[-1]:
                            route_path.append(TOPOLOGY[hop_ip]["name"])
                    else:
                        route_path.append(hop_ip)
                        
        path_string = " → ".join(route_path)
        log_lines = [line.strip() for line in log_text.strip().split('\n') if line.strip()]
        last_line = log_lines[-1] if log_lines else ""
        
        is_finished_normally = "trace complete" in log_text.lower() or "トレースを完了" in log_text or (dst_ip and dst_ip in last_line) or (dst_node and dst_node["name"] in route_path[-1])
        
        if is_finished_normally and not has_error_message:
            result["status"] = "OK"
            result["summary"] = f"疎通確認。経路: {path_string}"
            result["layer_issue"] = "なし (正常)"
        else:
            result["status"] = "NG"
            if has_error_message:
                result["summary"] = f"ルータにより遮断されました。途絶した経路: {path_string}"
                result["layer_issue"] = "L3 (ルーティング不在)"
            else:
                result["summary"] = f"目的地手前でタイムアウトしました。途絶した経路: {path_string}"
                result["layer_issue"] = "L3 (ルーティングエラー、または戻り経路なし)"

    return result

@app.route('/')
def index():
    device_list = [{"ip": ip, "name": info["name"], "type": info["type"]} for ip, info in TOPOLOGY.items() if info["type"] in ["PC", "Router"]]
    device_list.sort(key=lambda x: (x["type"], x["name"]))
    
    pc_names = [info["name"] for info in TOPOLOGY.values() if info["type"] == "PC"]
    pc_names.sort()
    
    # マトリクスマップを現在の履歴ベースで最新の状態に更新
    recalculate_matrix()
    
    # 履歴を逆順（最新が上）にして、直近5件だけ切り取る
    recent_records = list(reversed(dashboard_records))[:5]
    
    return render_template('index.html', 
                           records=recent_records, 
                           device_list=device_list, 
                           matrix_status=matrix_status, 
                           pc_names=pc_names)

@app.route('/submit', methods=['POST'])
def submit():
    log_text = request.form.get('log_text', '')
    src_ip = request.form.get('src_ip', '')
    
    if log_text.strip():
        analysis = analyze_log(log_text, src_ip)
        dashboard_records.append(analysis)
    return redirect(url_for('index'))

@app.route('/delete/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    """指定されたIDの履歴を削除するエンドポイント"""
    global dashboard_records
    # 指定されたID以外のレコードだけを残す（＝対象を削除する）
    dashboard_records = [r for r in dashboard_records if r["id"] != record_id]
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
