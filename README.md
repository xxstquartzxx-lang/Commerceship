# RPP広告 × 商品データ分析ツール

楽天の「RPP広告データ」と「商品分析データ」を掛け合わせ、相関分析や有望キーワードの発掘を行うツールです。

## 使い方のヒント
1. **データ準備**: RMSからダウンロードしたCSVファイルを用意します。
2. **アップロード**: 商品データとRPPデータをそれぞれの枠にドラッグ＆ドロップします。
3. **分析**:
    - **Tab 1**: データの結合状態を確認
    - **Tab 2**: 散布図で「お宝キーワード」や「無駄遣いキーワード」を発見
    - **Tab 3**: 売上や転換率に本当に効いている要素をヒートマップで特定

## Webアプリとして起動
以下のボタンをクリックすると、Streamlit Cloud上でこのツールを起動できます。

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=xxstquartzxx-lang/Commerceship&branch=main&mainModule=app.py)
