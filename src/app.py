import re
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# トポロジ図に基づく機器データベース
TOPOLOGY = {
    # 左側サイト（黄：Router1配下）
    "192.168.10.1":   {"name": "PC0", "vlan": 10, "site": "Left", "type": "PC"},
    "192.168.10.2":   {"name": "PC2", "vlan": 10, "site": "Left", "type": "PC"},
    "192.168.10.254": {"name": "R1_VLAN10_GW", "vlan": 10, "site": "Left", "type": "GW"},
    
    "192.168.20.1":   {"name": "PC1", "vlan": 20, "site": "Left", "type": "PC"},
    "192.168.20.2":   {"name": "PC3", "vlan": 20, "site": "Left", "type": "PC"},
    "192.168.20.254": {"name": "R1_VLAN20_GW", "vlan": 20, "site": "Left", "type": "GW"},
    
    "192.168.100.1":  {"name": "Router1", "vlan": None, "site": "Left", "type": "Router"},

    # 右側サイト（水色：Router2配下）
    "192.168.30.1":   {"name": "PC4", "vlan": 30, "site": "Right", "type": "PC"},
    "192.168.30.2":   {"name": "PC6", "vlan": 30, "site": "Right", "type": "PC"},
    "192.168.30.254": {"name": "R2_VLAN30_GW", "vlan": 30, "site": "Right", "type": "GW"},
    
    "192.168.40.1":   {"name": "PC5", "vlan": 40, "site": "Right", "type": "PC"},
    "192.168.40.2":   {"name": "PC7", "vlan": 40, "site": "Right", "type": "PC"},
    "192.168.40.254": {"name": "R2_VLAN40_GW", "vlan": 40, "site": "Right", "type": "GW"},
    
    "192.168.100.2":  {"name": "Router2", "vlan": None, "site": "Right", "type": "Router"},
}

dashboard_records = []
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

init_matrix()

def analyze_log(log_text, src_ip):
    result = {
        "command_type": "Unknown",
        "status": "Unknown",
        "src_info": "未指定",
        "dst_info": "なし",
        "comm_type": "判定不可",
        "summary": "ログを解析できませんでした",
        "layer_issue": "なし (正常)",
    }
    
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
    if "ping" in log_text.lower() or "reply from" in log_text.lower():
        result["command_type"] = "ping"
        dst_match = re.search(r"(?:Pinging|ping)\s+([0-9\.]+)", log_text, re.IGNORECASE)
        dst_ip = dst_match.group(1) if dst_match else None

        dst_node = None
        if dst_ip:
            dst_node = TOPOLOGY.get(dst_ip)
            if dst_node:
                result["dst_info"] = dst_node["name"]
            else:
                result["dst_info"] = f"トポロジ外 ({dst_ip})"

                # 【修正ポイント】成功・失敗判定の優先順位を厳密化
        if "unreachable" in log_text.lower():
            result["status"] = "NG"
            result["layer_issue"] = "L3 (ルーティング不在)"
            result["summary"] = "宛先への経路情報がありません（一部または全部がUnreachable）"
            
        elif "timed out" in log_text.lower():
            # 1発でもタイムアウトがあれば失敗（NG）扱いにする
            result["status"] = "NG"
            if "reply from" in log_text.lower() and "bytes=" in log_text.lower():
                result["summary"] = "一部のパケットが損失しました（ARP解決遅延、またはネットワークの不安定）"
                result["layer_issue"] = "L2 (ARP未解決などによる初回ドロップの可能性)"
            else:
                result["summary"] = "相手からの応答が一切ありません（物理断、VLANミス、またはFW遮断）"
                result["layer_issue"] = "L1/L2 (物理・VLAN) または L3 (戻り経路なし)"
                
        elif "100% loss" in log_text:
            result["status"] = "NG"
            result["summary"] = "通信が完全に遮断されています"
            result["layer_issue"] = "L1-L3のいずれかで致命的な切断"
            
        elif "reply from" in log_text.lower() and "bytes=" in log_text.lower():
            # 1発もエラー行がなく、すべてきれいに通った場合のみ成功とする
            result["status"] = "OK"
            result["summary"] = "正常に通信が完了しました (100%到達)"
            result["layer_issue"] = "なし (正常)"

        if dst_node:
            if src_node["site"] != dst_node["site"]: result["comm_type"] = "遠隔サイト通信"
            elif src_node.get("vlan") != dst_node.get("vlan"): result["comm_type"] = "異なるVLAN間通信"
            else: result["comm_type"] = "同一VLAN間通信"
            
            # 送信元も宛先もPCの場合のみマトリクスを更新
            if src_node["type"] == "PC" and dst_node["type"] == "PC":
                matrix_status[src_node["name"]][dst_node["name"]] = result["status"]
        else:
            result["comm_type"] = "トポロジ外への通信"

    # --- 3. TRACERTの解析 ---
    elif "tracing" in log_text.lower() or "traceroute" in log_text.lower():
        result["command_type"] = "tracert"
        dst_match = re.search(r"(?:tracing route to|traceroute to)\s+([0-9\.]+)", log_text, re.IGNORECASE)
        dst_ip = dst_match.group(1) if dst_match else None
        
        dst_node = TOPOLOGY.get(dst_ip) if dst_ip else None
        if dst_node:
            result["dst_info"] = dst_node["name"]
            if src_node["site"] != dst_node["site"]: result["comm_type"] = "遠隔サイト通信"
            elif src_node.get("vlan") != dst_node.get("vlan"): result["comm_type"] = "異なるVLAN間通信"
            else: result["comm_type"] = "同一VLAN間通信"

        if "trace complete" in log_text.lower():
            result["status"] = "OK"
            result["summary"] = "目的地までの経路疎通を確認"
            result["layer_issue"] = "なし (正常)"
        else:
            result["status"] = "NG"
            result["summary"] = "途中で経路が途絶えています"
            result["layer_issue"] = "L3 (ルーティングエラー)"
            
        if dst_node and src_node["type"] == "PC" and dst_node["type"] == "PC":
            matrix_status[src_node["name"]][dst_node["name"]] = result["status"]

    return result

@app.route('/')
def index():
    # セレクトボックス用に全機器（PCとルータ両方）を並べ替え
    device_list = [{"ip": ip, "name": info["name"], "type": info["type"]} for ip, info in TOPOLOGY.items() if info["type"] in ["PC", "Router"]]
    device_list.sort(key=lambda x: (x["type"], x["name"]))
    
    pc_names = [info["name"] for info in TOPOLOGY.values() if info["type"] == "PC"]
    pc_names.sort()
    
    # 【修正ポイント】履歴リストを逆順（最新が上）にして、直近の5件だけを画面に渡す
    recent_records = list(reversed(dashboard_records))[:5]
    
    return render_template('index.html', 
                           records=recent_records, # 5件に絞った最新の履歴を渡す
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
