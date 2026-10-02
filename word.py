import io
import random
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from supabase import Client, create_client

st.set_page_config(page_title="英単語テスト生成ツール", layout="wide")


# --- Supabase 初期化 ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


try:
    supabase = init_supabase()
except Exception:
    st.error(
        "Supabaseの初期化に失敗しました。.streamlit/secrets.toml の設定を確認してください。"
    )
    st.stop()


# --- DB操作関数 ---
def fetch_words():
    try:
        response = (
            supabase.table("words")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return response.data
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return []


def add_word(word: str, meaning: str):
    try:
        response = (
            supabase.table("words")
            .insert({"word": word, "meaning": meaning})
            .execute()
        )
        return response.data
    except Exception as e:
        st.error(f"データ追加エラー: {e}")
        return None


# --- PDF生成関数（修正箇所） ---
def generate_pdf(df_target):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    width, height = A4

    # ================= 1. 問題用紙の作成 =================
    c.setFont("HeiseiKakuGo-W5", 16)
    c.drawString(50, height - 50, "英単語テスト")

    c.setFont("HeiseiKakuGo-W5", 10)
    c.drawString(400, height - 50, "氏名:__________________________")

    c.setLineWidth(0.5)
    c.line(50, height - 70, 550, height - 70)

    y = height - 100
    c.setFont("HeiseiKakuGo-W5", 12)

    for idx, row in enumerate(df_target.itertuples(), start=1):
        text = f"Q.{idx}. {row.word} : __________________________"
        c.drawString(50, y, text)
        y -= 30
        if y < 50:
            c.showPage()
            c.setFont("HeiseiKakuGo-W5", 12)
            y = height - 50

    # 解答ページへ改ページ
    c.showPage()

    # ================= 2. 解答用紙の作成 =================
    c.setFont("HeiseiKakuGo-W5", 16)
    c.drawString(50, height - 50, "英単語テスト【解答】")

    c.setLineWidth(0.5)
    c.line(50, height - 70, 550, height - 70)

    y = height - 100
    c.setFont("HeiseiKakuGo-W5", 12)

    for idx, row in enumerate(df_target.itertuples(), start=1):
        text = f"Q.{idx}. {row.word} : {row.meaning}"
        c.drawString(50, y, text)
        y -= 30
        if y < 50:
            c.showPage()
            c.setFont("HeiseiKakuGo-W5", 12)
            y = height - 50

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


# --- 画面レイアウト ---
st.title("英単語テスト生成ツール")

# サイドバー 1: 手動追加
st.sidebar.header("1. 単語を手動追加")
with st.sidebar.form("add_word_form", clear_on_submit=True):
    word = st.text_input("単語")
    meaning = st.text_input("意味")
    submitted = st.form_submit_button("追加")

    if submitted:
        if word and meaning:
            res = add_word(word, meaning)
            if res:
                st.success(f"単語 '{word}' が追加されました。")
                st.rerun()
        else:
            st.error("単語と意味の両方を入力してください。")

# サイドバー 2: CSVファイルから追加
st.sidebar.markdown("---")
st.sidebar.header("2. CSVから一括追加")
uploaded_file = st.sidebar.file_uploader(
    "単語帳CSVを選択 (列: word, meaning)", type=["csv"]
)
if uploaded_file is not None:
    if st.sidebar.button("DBに一括保存"):
        try:
            bulk_df = pd.read_csv(uploaded_file)
            if "word" in bulk_df.columns and "meaning" in bulk_df.columns:
                records = bulk_df[["word", "meaning"]].to_dict(
                    orient="records"
                )
                supabase.table("words").insert(records).execute()
                st.sidebar.success(f"{len(records)}件を追加しました！")
                st.rerun()
            else:
                st.sidebar.error("CSVに 'word' と 'meaning' 列が必要です。")
        except Exception as e:
            st.sidebar.error(f"エラー: {e}")

# データ取得
words_data = fetch_words()
df = pd.DataFrame(words_data)

tab1, tab2 = st.tabs(["単語一覧", "テスト生成"])

with tab1:
    st.subheader("登録済み単語一覧")
    if not df.empty and "id" in df.columns:
        st.caption(f"全 {len(df)} 件の単語が登録されています。")
        # 検索フィルター
        search_query = st.text_input("単語・意味で検索", "")
        if search_query:
            filtered_df = df[
                df["word"].str.contains(search_query, case=False, na=False)
                | df["meaning"].str.contains(
                    search_query, case=False, na=False
                )
            ]
        else:
            filtered_df = df

        display_df = filtered_df[["id", "word", "meaning", "created_at"]]
        st.dataframe(display_df, use_container_width=True, height=400)
    else:
        st.info("まだ単語が登録されていません。")

with tab2:
    st.subheader("テスト生成")
    if df.empty:
        st.warning("単語が登録されていないため、テストを生成できません。")
    else:
        max_count = len(df)
        test_count = st.number_input(
            "テストに出題する単語数",
            min_value=1,
            max_value=max_count,
            value=min(10, max_count),
        )

        if st.button("ランダムにテスト生成"):
            random_indices = random.sample(range(max_count), test_count)
            st.session_state["test_df"] = df.iloc[
                random_indices
            ].reset_index(drop=True)

        if "test_df" in st.session_state:
            test_df = st.session_state["test_df"]
            st.markdown("---")
            st.write("### テストプレビュー")

            preview_df = test_df[["word"]].copy()
            preview_df["回答欄"] = "__________________________"
            st.table(preview_df)

            col1, col2 = st.columns(2)
            with col1:
                csv_data = (
                    test_df[["word", "meaning"]]
                    .to_csv(index=False)
                    .encode("utf-8-sig")
                )
                st.download_button(
                    label="解答用CSVダウンロード",
                    data=csv_data,
                    file_name="英単語テスト_解答.csv",
                    mime="text/csv",
                )

            with col2:
                pdf_buffer = generate_pdf(test_df)
                st.download_button(
                    label="テスト・解答PDFをダウンロード",
                    data=pdf_buffer,
                    file_name="英単語テスト_問題と解答.pdf",
                    mime="application/pdf",
                )