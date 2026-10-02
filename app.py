"""다국어 번역기 Streamlit 앱."""

import streamlit as st

from translator import (
    TranslationError,
    TranslationResult,
    get_api_key,
    get_model,
    translate_all,
    translate_stream,
)

st.set_page_config(page_title="다국어 번역기", page_icon="🌐", layout="centered")

MAX_CHARS = 5000
WARN_CHARS = 4500
LANGUAGE_LABELS = {"en": "🇺🇸 영어", "ja": "🇯🇵 일본어", "vi": "🇻🇳 베트남어"}
TAB_LABELS = {"en": "🇺🇸 English", "ja": "🇯🇵 日本語", "vi": "🇻🇳 Tiếng Việt"}

CUSTOM_CSS = """
<style>
.char-counter { text-align: right; font-size: 0.85rem; opacity: 0.65; margin-top: -0.75rem; }
.char-counter.warn { color: #D97706; opacity: 1; }
.char-counter.limit { color: #DC2626; opacity: 1; font-weight: 600; }
.empty-result {
    text-align: center; padding: 2.5rem 1rem; opacity: 0.55;
    border: 1px dashed currentColor; border-radius: 0.75rem;
}
/* 번역 결과의 복사 버튼을 마우스를 올리지 않아도(모바일 포함) 항상 보이게 한다. */
[data-testid="stCode"] div:has([data-testid="stElementToolbarButton"]) { opacity: 1 !important; visibility: visible !important; }
[data-testid="stCode"] pre { padding-right: 3rem; }
.app-footer { text-align: center; font-size: 0.8rem; opacity: 0.55; margin-top: 3rem; }
</style>
"""

st.session_state.setdefault("translating", False)
st.session_state.setdefault("last", None)  # {"text": 원문, "results": {code: TranslationResult}}
st.session_state.setdefault("notice", None)  # 다음 실행에 보여줄 입력 검증 경고


def validate(text: str, languages: list[str]) -> str | None:
    """입력값을 검사해 문제가 있으면 경고 메시지를, 없으면 None을 반환한다."""
    if not text.strip():
        return "번역할 글을 입력해주세요."
    if not languages:
        return "번역할 언어를 하나 이상 선택해주세요."
    if len(text) > MAX_CHARS:
        return f"최대 {MAX_CHARS:,}자까지 입력할 수 있습니다."
    return None


def start_translation() -> None:
    """번역 버튼 콜백. 번역 중 상태로 바꿔 버튼을 비활성화한다."""
    st.session_state.translating = True


def render_char_counter(length: int) -> None:
    """입력 글자 수를 표시한다. 한도에 가까워지면 주황, 한도에 도달하면 빨강으로 바뀐다."""
    level = "limit" if length >= MAX_CHARS else "warn" if length >= WARN_CHARS else ""
    st.markdown(
        f'<div class="char-counter {level}">{length:,} / {MAX_CHARS:,}</div>',
        unsafe_allow_html=True,
    )


def stream_translations(text: str, languages: list[str]) -> dict[str, TranslationResult]:
    """언어별로 순서대로 번역하며 결과를 실시간으로 화면에 출력한다."""
    results = {}
    for code in languages:
        with st.container(border=True):
            st.markdown(f"**{TAB_LABELS[code]}**")
            try:
                translated = st.write_stream(translate_stream(text, code))
                if not isinstance(translated, str):
                    translated = "".join(map(str, translated))
                results[code] = TranslationResult(language=code, text=translated.strip())
            except TranslationError as exc:
                st.error(str(exc))
                results[code] = TranslationResult(language=code, error=str(exc))
    return results


def render_results(results: dict[str, TranslationResult]) -> None:
    """번역 결과를 언어별 탭으로 표시한다. 실패한 언어 탭에는 오류만 표시한다."""
    tabs = st.tabs([TAB_LABELS[code] for code in results])
    for tab, result in zip(tabs, results.values()):
        with tab:
            if result.error:
                st.error(result.error, icon="⚠️")
            else:
                st.code(result.text, language=None, wrap_lines=True)
                st.caption("오른쪽 위 복사 버튼을 누르면 결과가 복사됩니다.")


has_api_key = bool(get_api_key())
model = get_model()

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

with st.sidebar:
    st.subheader("⚙️ 설정")
    st.write(f"사용 모델: `{model}`")
    use_stream = st.toggle(
        "실시간 출력",
        help="번역 결과를 생성되는 대로 보여줍니다. 언어별로 순서대로 번역하므로 조금 더 오래 걸립니다.",
    )
    st.divider()
    st.subheader("📖 사용 방법")
    st.markdown(
        "1. 번역할 글을 입력합니다.\n"
        "2. 번역할 언어를 선택합니다.\n"
        "3. **번역하기**를 누르고 결과를 복사합니다."
    )
    st.caption(f"한 번에 최대 {MAX_CHARS:,}자까지 번역할 수 있습니다.")

st.title("🌐 다국어 번역기")
st.caption("입력한 글을 영어 · 일본어 · 베트남어로 한 번에 번역합니다.")

if not has_api_key:
    st.error("API 키가 설정되지 않았습니다. .env 또는 Secrets를 확인하세요.", icon="🔑")

text = st.text_area(
    "번역할 글",
    placeholder="번역할 글을 입력하세요... (원문 언어는 자동으로 감지됩니다)",
    max_chars=MAX_CHARS,
    height=200,
    key="input_text",
)
render_char_counter(len(text))

st.markdown("**번역할 언어**")
selected = [
    code
    for column, (code, label) in zip(st.columns(len(LANGUAGE_LABELS)), LANGUAGE_LABELS.items())
    if column.checkbox(label, value=True, key=f"lang_{code}")
]

st.button(
    "번역 중..." if st.session_state.translating else "번역하기",
    type="primary",
    width="stretch",
    on_click=start_translation,
    disabled=not has_api_key or st.session_state.translating,
)

if st.session_state.notice:
    st.warning(st.session_state.notice, icon="✏️")
    st.session_state.notice = None

st.divider()

if st.session_state.translating:
    try:
        notice = validate(text, selected)
        if notice:
            st.session_state.notice = notice
        elif use_stream:
            st.session_state.last = {"text": text, "results": stream_translations(text, selected)}
        else:
            with st.spinner("번역 중입니다..."):
                st.session_state.last = {"text": text, "results": translate_all(text, selected)}
    finally:
        st.session_state.translating = False
    # 버튼을 다시 활성화하고 저장된 결과로 화면을 그리기 위해 다시 실행한다.
    st.rerun()

if st.session_state.last:
    render_results(st.session_state.last["results"])
else:
    st.markdown('<div class="empty-result">번역 결과가 여기에 표시됩니다</div>', unsafe_allow_html=True)

st.markdown(f'<div class="app-footer">Powered by {model}</div>', unsafe_allow_html=True)
