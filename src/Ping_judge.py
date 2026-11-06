
nodes_PC = ["pc0", "pc1", "pc2", "pc3", "pc4", "pc5", "pc6", "pc7"]
edges_PC = {(a, b): None for a in nodes_PC for b in nodes_PC if a != b}


class Ping_judge:
    def __init__(self):
        # PC間の通信可否を記録する辞書
        self.edges_PC = edges_PC.copy()

    def set_Ping_judge(self, start, end, judge):
        # 通信結果を1または0に変換
        judge = 1 if judge else 0

        # 指定されたedgeの通信結果を記録
        if (start, end) in self.edges_PC:
            self.edges_PC[(start, end)] = judge
        else:
            raise ValueError(f"Invalid edge: {start} -> {end}")


if __name__ == "__main__":
    print(nodes_PC)
    print(edges_PC)

    ping = Ping_judge()

    # 通信結果の記録
    start = input("start:")
    end = input("end:")
    judge = int(input("judge:"))
    ping.set_Ping_judge(start, end, judge)

    print(ping.edges_PC)
