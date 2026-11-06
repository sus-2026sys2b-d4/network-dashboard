# network-dashboard

## 1. 環境構築手順（Windows | PowerShell）
1. 適当なディレクトリで以下のコマンドを実行する。
```bash
git clone https://github.com/sus-2026sys2b-d4/network-dashboard
cd ./network-dashboard
```

2. 以下のコマンドで仮想環境を作成する
```bash
py -3.12 -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
3. 以下のコマンドを実行し、必要なライブラリをインストールする
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```
4. hello.pyを実行して動作確認する


## 2. 環境構築手順（Ubuntu）
1. 適当なディレクトリで以下のコマンドを実行する。
```bash
git clone https://github.com/sus-2026sys2b-d4/network-dashboard
cd ./network-dashboard
```

2. 以下のコマンドで仮想環境を作成する
```bash
python3.12 -m venv .venv
source ./.venv/bin/activate
```
3. 以下のコマンドを実行し、必要なライブラリをインストールする
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```
4. hello.pyを実行して動作確認する