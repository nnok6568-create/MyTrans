"""OpenAI API를 사용한 번역 로직."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import openai
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DEFAULT_MODEL = "gpt-6-astra"
REQUEST_TIMEOUT = 60  # 초
MAX_RETRIES = 1

SUPPORTED_LANGUAGES = {
    "en": "English",
    "ja": "Japanese",
    "vi": "Vietnamese",
}

SYSTEM_PROMPT = """You are a professional translator.
Translate the user's text into {target_language}.
- Preserve meaning, tone, formatting, line breaks.
- Do not translate proper nouns, numbers, URLs, or emojis unless necessary.
- Output only the translated text, with no explanations."""


class TranslationError(Exception):
    """사용자에게 그대로 보여줄 수 있는 한국어 메시지를 담은 번역 오류."""


@dataclass
class TranslationResult:
    """한 언어의 번역 결과. 성공하면 text, 실패하면 error가 채워진다."""

    language: str
    text: str | None = None
    error: str | None = None


def get_setting(name: str, default: str | None = None) -> str | None:
    """설정값을 st.secrets → 환경 변수(.env) → 기본값 순서로 읽는다."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        # secrets.toml이 없으면 st.secrets 접근 시 예외가 발생하므로 무시한다.
        pass
    return os.getenv(name) or default


def get_api_key() -> str | None:
    """OpenAI API 키를 반환한다."""
    return get_setting("OPENAI_API_KEY")


def get_model() -> str:
    """번역에 사용할 모델명을 반환한다."""
    return get_setting("OPENAI_MODEL", DEFAULT_MODEL)


def create_client() -> OpenAI:
    """타임아웃·재시도가 설정된 OpenAI 클라이언트를 만든다. API 키가 없으면 TranslationError."""
    api_key = get_api_key()
    if not api_key:
        raise TranslationError("API 키가 설정되지 않았습니다. .env 또는 Secrets를 확인하세요.")
    return OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=MAX_RETRIES)


def to_user_message(exc: Exception, model: str) -> str:
    """OpenAI 예외를 PRD 11절의 한국어 사용자 메시지로 변환한다."""
    if isinstance(exc, TranslationError):
        return str(exc)
    if isinstance(exc, openai.AuthenticationError):
        return "API 키가 올바르지 않습니다. .env 또는 Secrets를 확인하세요."
    if isinstance(exc, openai.RateLimitError):
        return "요청이 많습니다. 잠시 후 다시 시도해주세요."
    if isinstance(exc, (openai.NotFoundError, openai.PermissionDeniedError)):
        return f"모델({model})을 사용할 수 없습니다. 모델명과 계정 권한을 확인하세요."
    if isinstance(exc, openai.APITimeoutError):
        return "응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
    if isinstance(exc, openai.APIConnectionError):
        return "네트워크 연결에 실패했습니다. 인터넷 연결을 확인해주세요."
    return "번역 중 오류가 발생했습니다. 다시 시도해주세요."


def _build_messages(text: str, target_language: str) -> list[dict]:
    """번역 요청 메시지를 만든다."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(target_language=target_language)},
        {"role": "user", "content": text},
    ]


def translate(
    text: str,
    target_language: str,
    client: OpenAI | None = None,
    model: str | None = None,
) -> str:
    """text를 target_language(예: "English")로 번역해 반환한다. 실패하면 TranslationError."""
    model = model or get_model()
    try:
        client = client or create_client()
        response = client.chat.completions.create(
            model=model,
            messages=_build_messages(text, target_language),
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        raise TranslationError(to_user_message(exc, model)) from exc


def translate_all(text: str, languages: list[str]) -> dict[str, TranslationResult]:
    """languages(언어 코드 목록)로 동시에 번역한다. 한 언어가 실패해도 나머지 결과는 반환한다."""
    # st.secrets는 메인 스레드에서만 읽고, 작업 스레드에는 클라이언트와 모델명을 넘긴다.
    model = get_model()
    try:
        client = create_client()
    except TranslationError as exc:
        return {code: TranslationResult(language=code, error=str(exc)) for code in languages}

    def work(code: str) -> TranslationResult:
        try:
            translated = translate(text, SUPPORTED_LANGUAGES[code], client=client, model=model)
            return TranslationResult(language=code, text=translated)
        except TranslationError as exc:
            return TranslationResult(language=code, error=str(exc))

    with ThreadPoolExecutor(max_workers=len(languages) or 1) as executor:
        results = list(executor.map(work, languages))
    return {result.language: result for result in results}


def translate_stream(text: str, language: str) -> Iterator[str]:
    """language(언어 코드)로 번역하며 결과를 토큰 단위로 yield한다. 실패하면 TranslationError."""
    model = get_model()
    try:
        client = create_client()
        stream = client.chat.completions.create(
            model=model,
            messages=_build_messages(text, SUPPORTED_LANGUAGES[language]),
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as exc:
        raise TranslationError(to_user_message(exc, model)) from exc
