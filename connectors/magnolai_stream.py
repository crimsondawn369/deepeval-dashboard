"""
MagnolaiStreamConnector

Confirmed against DIGH_DE_Magnolai_Web/aichat-api/src/:
  - Session create:  POST  {base_url}{stream_path}
                     body: {"session_id": "00000000-0000-0000-0000-000000000000",
                             "user_input": "", "analysis_type": "<type>"}
                     The backend detects INIT_USER_ID, calls welcome(), creates a real
                     session in DB, and returns {"transfer_status":"success",
                     "data":{"session_id":"<uuid>",...}} — the session_id in data is used.
                     This mirrors how the Angular app bootstraps sessions.
  - Stream:          POST  {base_url}{stream_path}
                     body: {"session_id": "<uuid>", "user_input": "<question>",
                             "analysis_type": "<type>"}
                     response: chunked text, frames delimited by ##&&##
                     each frame: {"transfer_status": "success|heartbeat|error",
                                  "data": {"content": "...", "source": [...]}}
  - Delete:          DELETE {base_url}/api/v1/aiquery?id=<uuid>
                     (id is a query param — confirmed in Angular ai-query.service.ts)
"""
import json
import logging
import os
import time

import httpx

from auth.cookie_manager import get_cookie_manager
from connectors.base import AppConnector

DELIMITER = "##&&##"
logger = logging.getLogger(__name__)


class MagnolaiStreamConnector(AppConnector):
    def __init__(self, stream_config: dict):
        env = os.getenv("MAGNOLAI_ENV", "dev")
        self._name: str = stream_config["id"]
        self._display_name: str = stream_config["display_name"]
        self._base_url: str = stream_config["base_url"].replace("{env}", env)
        self._chat_url: str = stream_config["chat_url"].replace("{env}", env)
        self._stream_path: str = stream_config["stream_path"]
        self._analysis_type: str = stream_config["analysis_type"]
        self._model: str = os.getenv("MAGNOLAI_MODEL", "gpt-5.4")
        self.cookie_manager = get_cookie_manager(self._chat_url)

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    def _headers(self) -> dict:
        auth = self.cookie_manager.get_cookie_header()
        if auth.startswith("Bearer "):
            logger.info("[auth] using Bearer token (len=%d)", len(auth))
            return {"Authorization": auth, "Content-Type": "application/json"}
        logger.info("[auth] using Cookie fallback: %s", auth.split("=", 1)[0])
        return {"Cookie": auth, "Content-Type": "application/json"}

    INIT_USER_ID = "00000000-0000-0000-0000-000000000000"

    def _create_session(self) -> str:
        """Bootstrap a session the same way the Angular app does.

        Sends a stream request with INIT_USER_ID so the backend calls welcome(),
        creates a proper AppQueries record with SessionType set, and returns the
        new session_id in the first success frame.
        """
        url = self._base_url + self._stream_path
        payload = {
            "session_id": self.INIT_USER_ID,
            "user_input": "",
            "analysis_type": self._analysis_type,
            "model": self._model,
        }
        for attempt in range(2):
            try:
                buffer = ""
                session_id = None
                logger.info(
                    "[bootstrap] POST %s (attempt %d/2, analysis_type=%s, model=%s)",
                    url, attempt + 1, self._analysis_type, self._model,
                )
                with httpx.stream(
                    "POST", url, json=payload, headers=self._headers(), timeout=30
                ) as resp:
                    logger.info("[bootstrap] response status=%s", resp.status_code)
                    if resp.status_code == 401 and attempt == 0:
                        logger.warning("401 on session bootstrap — refreshing token and retrying")
                        self.cookie_manager.get_cookie_header(force_refresh=True)
                        continue
                    if resp.status_code == 503:
                        retry_after = resp.headers.get("Retry-After", "5")
                        raise ConnectionError(
                            f"Magnolai API returned 503 (Retry-After: {retry_after}s). "
                            "The server is at capacity — try again shortly."
                        )
                    resp.raise_for_status()
                    frame_count = 0
                    for chunk in resp.iter_text():
                        buffer += chunk
                        parts = buffer.split(DELIMITER)
                        for raw in parts[:-1]:
                            raw = raw.strip()
                            if not raw:
                                continue
                            try:
                                frame = json.loads(raw)
                            except json.JSONDecodeError:
                                logger.warning(
                                    "[bootstrap] skipping unparseable frame: %r", raw[:200]
                                )
                                continue
                            frame_count += 1
                            status = frame.get("transfer_status")
                            logger.debug("[bootstrap] frame #%d status=%s", frame_count, status)
                            if status == "heartbeat":
                                continue
                            data = frame.get("data") or {}
                            sid = data.get("session_id")
                            if sid:
                                session_id = str(sid)
                                resp.close()
                                break
                        if session_id:
                            break
                        buffer = parts[-1]

                    logger.info(
                        "[bootstrap] stream ended after %d frame(s), session_id=%s",
                        frame_count, session_id,
                    )
                if session_id:
                    logger.info("Bootstrap session created: %s", session_id)
                    return session_id

                if attempt == 0:
                    continue
                raise ValueError("Bootstrap stream ended without returning a session_id")

            except (ConnectionError, ValueError):
                raise
            except Exception as exc:
                if attempt == 0:
                    continue
                raise ConnectionError(f"Session bootstrap failed: {exc}") from exc

        raise ConnectionError("Session bootstrap failed after retry")

    def _delete_session(self, session_id: str) -> None:
        url = self._base_url + "/api/v1/aiquery"
        try:
            headers = self._headers()
            httpx.delete(url, params={"id": session_id}, headers=headers, timeout=10)
        except Exception as exc:
            logger.warning("Session delete failed for %s: %s", session_id, exc)

    def _consume_stream(self, session_id: str, question: str) -> tuple[str, list]:
        url = self._base_url + self._stream_path
        payload = {
            "session_id": session_id,
            "user_input": question,
            "analysis_type": self._analysis_type,
            "model": self._model,
        }
        content_parts: list[str] = []
        sources: list = []

        logger.info(
            "[stream] POST %s session_id=%s question=%r",
            url, session_id, question[:200],
        )

        with httpx.stream(
            "POST",
            url,
            json=payload,
            headers=self._headers(),
            timeout=300,
        ) as resp:
            logger.info("[stream] response status=%s", resp.status_code)
            if resp.status_code == 403:
                raise PermissionError(
                    f"403 Forbidden from stream endpoint {url}. "
                    "Your session does not have access to this stream."
                )
            resp.raise_for_status()

            buffer = ""
            frame_count = 0
            for chunk in resp.iter_text():
                buffer += chunk
                # Split on delimiter — never use an SSE parser
                parts = buffer.split(DELIMITER)
                # All parts except the last are complete frames
                for raw in parts[:-1]:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        frame = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Skipping unparseable frame: %r", raw[:120])
                        continue
                    frame_count += 1
                    status = frame.get("transfer_status")
                    logger.debug("[stream] frame #%d status=%s", frame_count, status)
                    if status == "heartbeat":
                        continue
                    if status == "error":
                        data_field = frame.get("data") or {}
                        error_msg = (
                            data_field.get("content")
                            or data_field.get("message")
                            or data_field.get("error")
                            or str(data_field) if data_field else None
                            or "The Magnolai backend returned an internal error."
                        )
                        logger.warning(
                            "Stream error frame — full frame: %s", json.dumps(frame)
                        )
                        return "".join(content_parts) or f"[Backend error: {error_msg}]", sources
                    data = frame.get("data") or {}
                    if data.get("content"):
                        content_parts.append(data["content"])
                    if data.get("source"):
                        sources.extend(data["source"])
                buffer = parts[-1]  # keep incomplete tail

            # Flush any remaining data after the stream ends
            tail = buffer.strip()
            if tail:
                try:
                    frame = json.loads(tail)
                    data = frame.get("data") or {}
                    if data.get("content"):
                        content_parts.append(data["content"])
                    if data.get("source"):
                        sources.extend(data["source"])
                except json.JSONDecodeError:
                    logger.warning("Skipping unparseable trailing frame: %r", tail[:200])

        answer = "".join(content_parts)
        logger.info(
            "[stream] done: %d frame(s), answer length=%d chars, %d source(s)",
            frame_count, len(answer), len(sources),
        )
        if not answer:
            logger.warning(
                "[stream] Magnolai returned an EMPTY answer for question=%r "
                "(session_id=%s) — %d frames were received but none carried "
                "non-empty data.content. Set logging to DEBUG to see raw frames.",
                question[:200], session_id, frame_count,
            )
        return answer, sources

    def query(self, question: str) -> tuple[str, list]:
        session_id: str | None = None
        last_exc: Exception | None = None

        logger.info("[query] stream=%s question=%r", self._name, question[:200])

        for attempt in range(3):
            try:
                session_id = self._create_session()
                answer, sources = self._consume_stream(session_id, question)
                logger.info(
                    "[query] stream=%s succeeded on attempt %d/3 — answer length=%d",
                    self._name, attempt + 1, len(answer),
                )
                return answer, sources
            except PermissionError:
                raise
            except (ConnectionError, TimeoutError, httpx.TimeoutException) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "Query attempt %d/3 failed (%s) — retrying in %ds",
                    attempt + 1, exc, wait,
                )
                time.sleep(wait)
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    wait = 2 ** attempt
                    logger.warning(
                        "Query attempt %d/3 failed (%s) — retrying in %ds",
                        attempt + 1, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    raise
            finally:
                if session_id:
                    self._delete_session(session_id)
                    session_id = None

        raise ConnectionError(
            f"All 3 query attempts failed. Last error: {last_exc}"
        ) from last_exc
