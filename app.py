import streamlit as st
import pandas as pd
import plotly.express as px
import chardet
import io
import re

# -----------------------------------------------------------------------------
# 1. ページ設定
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="RPP広告×商品データ分析ツール",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. ヘルパー関数: データ読み込み・前処理
# -----------------------------------------------------------------------------
def detect_encoding(file_buffer):
    """
    ファイルバッファのエンコーディングを判定する
    """
    raw_data = file_buffer.read(10000)
    file_buffer.seek(0)  # ファイルポインタを先頭に戻す
    result = chardet.detect(raw_data)
    encoding = result['encoding']
    
    # 日本語環境でよくある shift_jis と utf-8 の揺らぎを吸収
    if encoding and 'SHIFT_JIS' in encoding.upper():
        return 'cp932' # WindowsのShift_JIS拡張対応
    if encoding is None:
        return 'utf-8' # デフォルト
        
    return encoding

@st.cache_data
def load_csv_file(uploaded_file):
    """
    アップロードされたCSVファイルを読み込む（手動スライスによる確実なヘッダー抽出）
    """
    if uploaded_file is None:
        return None
    
    # バイトデータとして読み込む
    bytes_data = uploaded_file.getvalue()
    
    # エンコーディング判定
    encoding = detect_encoding(io.BytesIO(bytes_data))
    
    try:
        # テキストとして全行読み込み（ファイルサイズが極端に大きくない前提）
        text_io = io.TextIOWrapper(io.BytesIO(bytes_data), encoding=encoding, errors='replace')
        lines = text_io.readlines()
        
        header_index = -1
        sep = ','
        
        # ヘッダー行を探す
        for i, line in enumerate(lines[:100]): # 最初の100行を探索
            if "商品管理番号" in line:
                header_index = i
                # セパレータ判定
                if line.count('\t') > line.count(','):
                    sep = '\t'
                break
        
        if header_index != -1:
            # ヘッダー行以降のデータを結合してDataFrame化
            content = "".join(lines[header_index:])
            df = pd.read_csv(io.StringIO(content), sep=sep)
            return df
        else:
            st.warning("「商品管理番号」を含むヘッダー行が見つかりませんでした。通常の読み込みを試みます。")
            # フォールバック
            df = pd.read_csv(io.BytesIO(bytes_data), encoding=encoding)
            return df

    except Exception as e:
        st.error(f"読み込みエラー詳細: {e}")
        try:
             # 最後の手段：Pythonエンジン
             df = pd.read_csv(io.BytesIO(bytes_data), encoding=encoding, sep=None, engine='python')
             return df
        except:
             return None

def clean_currency(series):
    """
    金額文字列（例: "1,000円", "¥1000"）を数値に変換する
    """
    if series.dtype in ['int64', 'float64']:
        return series
    return series.astype(str).str.replace('円', '').str.replace('¥', '').str.replace(',', '').apply(pd.to_numeric, errors='coerce').fillna(0)

def clean_percent(series):
    """
    パーセント文字列（例: "5.0%", "12%"）を数値（0.05, 0.12）ではなく、そのままの数値（5.0, 12.0）として扱うことが一般的だが、
    要件や表示に合わせて調整。ここでは「%」をとって数値化する。
    例: "5.0%" -> 5.0
    """
    if series.dtype in ['int64', 'float64']:
        return series
    return series.astype(str).str.replace('%', '').str.replace(',', '').apply(pd.to_numeric, errors='coerce').fillna(0)

def preprocess_data(product_df, rpp_df):
    """
    データの結合とクリーニングを行う
    """
    # カラム名の正規化（空白除去・全角括弧の半角化）
    # ユーザ指摘の「記号は半角全角違う可能性」に対応
    rpp_df.columns = rpp_df.columns.str.strip().str.replace('（', '(').str.replace('）', ')')
    product_df.columns = product_df.columns.str.strip().str.replace('（', '(').str.replace('）', ')')

    # --- クリーニング (RPPデータ) ---
    # 数値化対象カラムのリスト (RPP)
    rpp_currency_cols = [
        '目安CPC', 'キーワードCPC', '実績額(合計)', 'CPC実績(合計)', 
        '実績額(新規)', 'CPC実績(新規)', '実績額(既存)', 'CPC実績(既存)', 
        '売上金額(合計12時間)', '注文獲得単価(合計12時間)', 
        '売上金額(合計720時間)', '注文獲得単価(合計720時間)'
    ]
    rpp_percent_cols = ['CTR(%)', 'CVR(合計12時間)(%)', 'ROAS(合計12時間)(%)', 'CVR(合計720時間)(%)', 'ROAS(合計720時間)(%)']
    rpp_int_cols = ['クリック数(合計)', 'クリック数(新規)', 'クリック数(既存)', '売上件数(合計12時間)', '売上件数(合計720時間)']

    for col in rpp_currency_cols:
        if col in rpp_df.columns:
            rpp_df[col] = clean_currency(rpp_df[col])
            
    for col in rpp_percent_cols:
        if col in rpp_df.columns:
            rpp_df[col] = clean_percent(rpp_df[col])

    for col in rpp_int_cols:
        if col in rpp_df.columns:
             # カンマが入っている場合にも対応
             rpp_df[col] = rpp_df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce').fillna(0).astype(int)

    # --- クリーニング (商品データ) ---
    # 数値化対象カラムのリスト (商品)
    product_currency_cols = ['売上', '客単価']
    product_percent_cols = ['転換率', '離脱率']
    product_int_cols = [
        '売上件数', '売上個数', 'アクセス人数', 'ユニークユーザー数', '総購入件数', 
        '新規購入件数', 'リピート購入件数', '未購入アクセス人数', 'レビュー投稿数', 
        '総レビュー数', '滞在時間（秒）', '直帰数', '離脱数', 'お気に入り登録ユーザ数', 
        'お気に入り総ユーザ数', '在庫数', '在庫0日日数'
    ]
    
    for col in product_currency_cols:
        if col in product_df.columns:
            product_df[col] = clean_currency(product_df[col])
            
    for col in product_percent_cols:
        if col in product_df.columns:
            product_df[col] = clean_percent(product_df[col])
            
    for col in product_int_cols:
        if col in product_df.columns:
             product_df[col] = product_df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce').fillna(0).astype(int)
    
    if 'レビュー総合評価（点）' in product_df.columns:
        product_df['レビュー総合評価（点）'] = pd.to_numeric(product_df['レビュー総合評価（点）'], errors='coerce').fillna(0)


    # --- 結合処理 ---
    # カラム名の空白除去
    rpp_df.columns = rpp_df.columns.str.strip()
    product_df.columns = product_df.columns.str.strip()

    # 商品管理番号をキーにする (文字列型に統一)
    if '商品管理番号' in rpp_df.columns:
        rpp_df['商品管理番号'] = rpp_df['商品管理番号'].astype(str)
    else:
        st.error(f"RPPデータに「商品管理番号」カラムが見つかりません。\n検出されたカラム: {', '.join(rpp_df.columns)}")
        st.markdown("### 読み込まれたデータ（先頭5行）")
        st.dataframe(rpp_df.head())
        return None

    if '商品管理番号' in product_df.columns:
        product_df['商品管理番号'] = product_df['商品管理番号'].astype(str)
    else:
        st.error(f"商品データに「商品管理番号」カラムが見つかりません。\n検出されたカラム: {', '.join(product_df.columns)}")
        st.markdown("### 読み込まれたデータ（先頭5行）")
        st.dataframe(product_df.head())
        return None

    # Left Join
    merged_df = pd.merge(rpp_df, product_df, on='商品管理番号', how='left', suffixes=('_RPP', '_商品'))
    
    return merged_df

# -----------------------------------------------------------------------------
# 3. サイドバー: ファイルアップロード & フィルタ設定
# -----------------------------------------------------------------------------
st.sidebar.title("設定パネル")

st.sidebar.header("1. データアップロード")
product_file = st.sidebar.file_uploader("商品データ (CSV)", type=['csv'])
rpp_file = st.sidebar.file_uploader("RPP広告データ (CSV)", type=['csv'])

st.sidebar.header("2. 分析フィルタ")
min_cpc = st.sidebar.slider("CPC実績(合計) の下限", 0, 500, 10, 5)
min_cvr = st.sidebar.slider("転換率 (商品データ) の下限 (%)", 0.0, 20.0, 0.0, 0.1)
min_clicks = st.sidebar.slider("クリック数(合計) の下限", 0, 1000, 10, 10)


# -----------------------------------------------------------------------------
# 4. メインロジック
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 4. メインロジック
# -----------------------------------------------------------------------------
st.title("RPP広告×商品データ分析ツール")

# レポートモード切替
st.sidebar.markdown("---")
report_mode = st.sidebar.checkbox("🖨️ レポート出力モード（印刷用表示）")

if report_mode:
    st.info("💡 この画面のまま、ブラウザの印刷機能（`Ctrl + P` または `Cmd + P`）を使い、「PDFに保存」を選択してください。A4横向き推奨です。")
    st.markdown("---")
    st.header("RPP広告 × 商品データ 相関分析レポート")

if product_file is not None and rpp_file is not None:
    # ショップ名の抽出（表示用変数の準備）
    shop_name_match = re.search(r'rpp_keyword_reports_([^_]+)_', rpp_file.name)
    shop_display_text = ""
    is_shop_found = False
    
    if shop_name_match:
        shop_name = shop_name_match.group(1)
        shop_display_text = f"📂 分析対象ショップ: **{shop_name}**"
        is_shop_found = True
    else:
        shop_display_text = f"📂 分析対象ファイル: {rpp_file.name}"
        is_shop_found = False

    # データ読み込み
    with st.spinner("データを読み込み中..."):
        product_df = load_csv_file(product_file)
        rpp_df = load_csv_file(rpp_file)
    
    if product_df is not None and rpp_df is not None:
        # データ前処理・結合
        merged_df = preprocess_data(product_df, rpp_df)
        
        if merged_df is not None:
            
            # --- レポートモードの場合の表示 ---
            if report_mode:
                # 相関分析の対象カラム
                target_cols_corr = [
                    'CPC実績(合計)', 'クリック数(合計)', 'ROAS(合計720時間)(%)', 
                    '転換率', '客単価', 'レビュー総合評価（点）', 
                    'CVR(合計720時間)(%)', 'CTR(%)',
                    '実績額(合計)'
                ]
                
                # 存在するカラムのみ抽出
                valid_corr_cols = [c for c in target_cols_corr if c in merged_df.columns]
                
                if len(valid_corr_cols) > 1:
                    corr_df = merged_df[valid_corr_cols].corr()
                    
                    # ヒートマップ
                    st.subheader("1. 指標間の相関ヒートマップ")
                    fig_corr = px.imshow(
                        corr_df,
                        text_auto='.2f',
                        aspect="auto",
                        color_continuous_scale='RdBu_r', # 赤-青
                    )
                    st.plotly_chart(fig_corr, use_container_width=True)
                    
                    # エビデンス（上位5件）
                    st.subheader("2. 特筆すべき相関トップ5（エビデンス）")
                    
                    # 結果をリストに格納してソートする
                    significant_correlations = []
                    cols = corr_df.columns
                    for i in range(len(cols)):
                        for j in range(i+1, len(cols)):
                            val = corr_df.iloc[i, j]
                            if abs(val) >= 0.3: # しきい値
                                significant_correlations.append({
                                    'col1': cols[i],
                                    'col2': cols[j],
                                    'val': val,
                                    'abs_val': abs(val)
                                })
                    
                    significant_correlations.sort(key=lambda x: x['abs_val'], reverse=True)
                    
                    if significant_correlations:
                        for i, item in enumerate(significant_correlations[:5]): # トップ5のみ
                            col1 = item['col1']
                            col2 = item['col2']
                            val = item['val']
                            relation = "正の相関（比例）" if val > 0 else "負の相関（反比例）"
                            strength = "強い" if abs(val) >= 0.7 else "中程度の" if abs(val) >= 0.5 else "弱い"
                            icon = "🔴" if val > 0 else "🔵"
                            
                            st.markdown(f"**{i+1}. {icon} {col1} × {col2} (係数: `{val:.2f}`)**")
                            st.write(f"- 傾向: {strength}{relation}")
                            
                            # 具体例
                            try:
                                valid_data = merged_df[[col1, col2, 'キーワード']].dropna()
                                if val > 0:
                                    merged_df['score_temp'] = (valid_data[col1] / valid_data[col1].max()) + (valid_data[col2] / valid_data[col2].max())
                                    top_examples = merged_df.loc[valid_data.index].sort_values('score_temp', ascending=False).head(2)
                                    st.caption(f"  例: {top_examples.iloc[0]['キーワード']} ({col1}:{top_examples.iloc[0][col1]}, {col2}:{top_examples.iloc[0][col2]}) など")
                                else:
                                    merged_df['score_temp'] = (valid_data[col1] / valid_data[col1].max()) - (valid_data[col2] / valid_data[col2].max())
                                    top_examples = merged_df.loc[valid_data.index].sort_values('score_temp', ascending=False).head(2)
                                    st.caption(f"  例: {top_examples.iloc[0]['キーワード']} ({col1}:{top_examples.iloc[0][col1]}, {col2}:{top_examples.iloc[0][col2]}) など")
                            except:
                                pass
                            st.markdown("---")
                    else:
                        st.info("特筆すべき強い相関関係（係数0.3以上）は見つかりませんでした。")

                else:
                    st.warning("相関分析を行うための十分なカラムが見つかりません。")

            # --- 通常モードの場合の表示 ---
            else:
                # タブの作成
                tab1, tab2, tab3 = st.tabs(["データプレビュー & 結合結果", "有望キーワード発掘（散布図）", "相関分析（ヒートマップ）"])
            
                # --- Tab 1: データプレビュー ---
                with tab1:
                    st.markdown("### データ結合結果")
                    st.write(f"RPPデータ行数: {len(rpp_df):,}")
                    st.write(f"結合後のデータ行数: {len(merged_df):,}")
                    st.write(f"カラム一覧: {', '.join(merged_df.columns)}")
                    st.dataframe(merged_df.head(100))
                    
                # --- Tab 2: 有望キーワード発掘 ---
                with tab2:
                    st.markdown("### 有望キーワード発掘マップ")
                    if is_shop_found:
                        st.success(shop_display_text)
                    else:
                        st.info(shop_display_text)
                    
                    st.info(f"フィルタ適用: CPC >= {min_cpc}円, CVR >= {min_cvr}%, クリック数 >= {min_clicks}回")
                    
                    # フィルタリング
                    # 必要なカラムが存在するかチェック
                    required_cols_scatter = ['CPC実績(合計)', '転換率', 'クリック数(合計)', 'ROAS(合計720時間)(%)']
                    missing_cols = [c for c in required_cols_scatter if c not in merged_df.columns]
                    
                    if not missing_cols:
                        filtered_df = merged_df[
                            (merged_df['CPC実績(合計)'] >= min_cpc) &
                            (merged_df['転換率'] >= min_cvr) &
                            (merged_df['クリック数(合計)'] >= min_clicks)
                        ].copy()
                        
                        if len(filtered_df) > 0:
                            # 散布図作成
                            # ホバーデータ用のカラム確認
                            hover_cols = ['キーワード', '商品名', '商品管理番号', '在庫数']
                            valid_hover_cols = [c for c in hover_cols if c in filtered_df.columns]
                            
                            fig = px.scatter(
                                filtered_df,
                                x='CPC実績(合計)',
                                y='転換率',
                                size='クリック数(合計)',
                                color='ROAS(合計720時間)(%)',
                                hover_data=valid_hover_cols,
                                title="キーワード分析マップ (サイズ: クリック数, 色: ROAS)",
                                labels={'CPC実績(合計)': 'CPC実績(円)', '転換率': '商品転換率(%)'},
                                height=600,
                                color_continuous_scale=px.colors.sequential.Viridis
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            
                            st.markdown("### 抽出データリスト")
                            st.dataframe(filtered_df)
                            
                            # CSVダウンロード
                            csv = filtered_df.to_csv(index=False, encoding='shift-jis', errors='ignore')
                            st.download_button(
                                label="抽出データをCSVでダウンロード",
                                data=csv,
                                file_name="rpp_analysis_filtered.csv",
                                mime="text/csv"
                            )
                        else:
                            st.warning("条件に該当するデータがありません。フィルタ設定を緩めてください。")
                    else:
                        st.error(f"分析に必要なカラムが不足しています: {missing_cols}")
    
                # --- Tab 3: 相関分析 ---
                with tab3:
                    st.markdown("### 重要指標の相関ヒートマップ")
                    if is_shop_found:
                        st.success(shop_display_text)
                    else:
                        st.info(shop_display_text)
                    
                    # 相関分析の対象カラム
                    target_cols_corr = [
                        'CPC実績(合計)', 'クリック数(合計)', 'ROAS(合計720時間)(%)', 
                        '転換率', '客単価', 'レビュー総合評価（点）', 
                        'CVR(合計720時間)(%)', 'CTR(%)',
                        '実績額(合計)'
                    ]
                    
                    # 存在するカラムのみ抽出
                    valid_corr_cols = [c for c in target_cols_corr if c in merged_df.columns]
                    
                    if len(valid_corr_cols) > 1:
                        corr_df = merged_df[valid_corr_cols].corr()
                        
                        fig_corr = px.imshow(
                            corr_df,
                            text_auto='.2f',
                            aspect="auto",
                            color_continuous_scale='RdBu_r', # 赤-青
                            title="指標間の相関係数"
                        )
                        st.plotly_chart(fig_corr, use_container_width=True)
                        
                        st.markdown("### 📊 分析結果の自動解説（エビデンス）")
                        # ユーザー要望により生データ表示は削除
                        
                        st.markdown("#### 特筆すべき相関関係と具体例（相関が強い順）:")
                        
                        # 結果をリストに格納してソートする
                        significant_correlations = []
                        
                        # 重複を除くために上三角行列のようなループ
                        cols = corr_df.columns
                        for i in range(len(cols)):
                            for j in range(i+1, len(cols)):
                                val = corr_df.iloc[i, j]
                                if abs(val) >= 0.3: # しきい値
                                    significant_correlations.append({
                                        'col1': cols[i],
                                        'col2': cols[j],
                                        'val': val,
                                        'abs_val': abs(val)
                                    })
                        
                        # 係数の絶対値で降順ソート
                        significant_correlations.sort(key=lambda x: x['abs_val'], reverse=True)
                        
                        if significant_correlations:
                            for item in significant_correlations:
                                col1 = item['col1']
                                col2 = item['col2']
                                val = item['val']
                                
                                relation = "正の相関（比例）" if val > 0 else "負の相関（反比例）"
                                strength = "強い" if abs(val) >= 0.7 else "中程度の" if abs(val) >= 0.5 else "弱い"
                                icon = "🔴" if val > 0 else "🔵"
                                
                                st.markdown(f"##### {icon} {col1} × {col2} (係数: `{val:.2f}`)")
                                st.write(f"**傾向**: {col1}が高い商品は、{col2}も{strength}{relation}する傾向があります。")
                                
                                # 具体的な商品のピックアップ (エビデンス)
                                try:
                                    # 両方の値がNaNでないデータを抽出
                                    valid_data = merged_df[[col1, col2, 'キーワード', '商品名']].dropna()
                                    
                                    if val > 0:
                                        # 正の相関の場合: 両方高いものをピックアップ
                                        merged_df['score_temp'] = (valid_data[col1] / valid_data[col1].max()) + (valid_data[col2] / valid_data[col2].max())
                                        top_examples = merged_df.loc[valid_data.index].sort_values('score_temp', ascending=False).head(3)
                                        
                                        st.markdown(f"**💡 この傾向を裏付ける代表的なキーワード（両方高い例）:**")
                                        for idx, row in top_examples.iterrows():
                                            st.text(f"・{row['キーワード']} ({col1}: {row[col1]}, {col2}: {row[col2]})")
                                            
                                    else:
                                        # 負の相関の場合: 片方が高く片方が低いものをピックアップ
                                        merged_df['score_temp'] = (valid_data[col1] / valid_data[col1].max()) - (valid_data[col2] / valid_data[col2].max())
                                        top_examples = merged_df.loc[valid_data.index].sort_values('score_temp', ascending=False).head(3) # Col1が高くてCol2が低い
                                        
                                        st.markdown(f"**💡 この傾向を裏付ける代表的なキーワード（{col1}が高く{col2}が低い例）:**")
                                        for idx, row in top_examples.iterrows():
                                            st.text(f"・{row['キーワード']} ({col1}: {row[col1]}, {col2}: {row[col2]})")
                                            
                                except Exception as e:
                                    # 計算エラー時はスキップ
                                    pass
                                
                                st.markdown("---")
                        
                        else:
                            st.info("特筆すべき強い相関関係（係数0.3以上）は見つかりませんでした。各指標は独立して動いているようです。")
                        
                    else:
                        st.warning("相関分析を行うための十分なカラムが見つかりません。")

else:
    # ファイル未アップロード時の表示
    st.info("サイドバーから「商品データ」と「RPP広告データ」の両方をアップロードしてください。")
    
    # サンプルとしてのガイダンス
    st.markdown("""
    ### 使い方
    1. 左側のサイドバーにある「Browse files」ボタンからCSVファイルをアップロードしてください。
    2. アップロードが完了すると、自動的にデータが結合され、分析画面が表示されます。
    3. スライダーを使って、分析対象のデータを絞り込むことができます。
    """)
