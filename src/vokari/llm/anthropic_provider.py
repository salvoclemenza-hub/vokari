"""Provider Claude via SDK Anthropic ufficiale. Thinking abilitato solo per chat_text."""

import anthropic

from vokari.llm.base import LLMError, parse_json_lenient

_MAX_TOKENS = 16000
# Claude ha ~200k token di contesto: budget di input prudente (lascia margine a system+output).
# L'analyzer riassume solo trascrizioni astronomicamente lunghe (>~135k parole, oltre 10h audio).
_INPUT_BUDGET_TOKENS = 180_000


class AnthropicProvider:
    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise LLMError("API key Anthropic non impostata. Esegui: vokari config set anthropic_api_key sk-ant-...")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def _create(self, system: str, user: str, *, thinking: bool = False):
        kwargs: dict = {}
        if thinking:
            # Thinking adaptive utile solo per output a testo libero (chat_text/refinement).
            # Su output JSON strutturato (chat_json) è overhead puro.
            kwargs["thinking"] = {"type": "adaptive"}
        return self._client.messages.create(
            model=self.model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            **kwargs,
        )

    @staticmethod
    def _text(response) -> str:
        # con thinking, il primo blocco può essere 'thinking': prendere il blocco text
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text.strip()
        raise LLMError("Risposta Anthropic priva di blocco testo.")

    def chat_json(self, system: str, user: str, *, json_schema: dict | None = None) -> dict:
        return parse_json_lenient(self._text(self._create(system, user, thinking=False)))

    def chat_text(self, system: str, user: str) -> str:
        return self._text(self._create(system, user, thinking=True))

    def context_budget_tokens(self) -> int:
        """Budget di input prudente sotto il contesto di Claude (~200k token). L'analyzer usa
        questo valore per decidere se riassumere; con Claude succede solo per trascrizioni
        astronomicamente lunghe."""
        return _INPUT_BUDGET_TOKENS

    def chat_json_stream(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        on_delta=None,
        should_cancel=None,
    ) -> dict:
        # thinking OFF come chat_json (su output JSON è overhead): text_stream emette il solo
        # testo JSON, che accumuliamo e parsiamo a fine stream — identico a chat_json ma con
        # i delta esposti via on_delta per l'anteprima live.
        acc = ""
        cancelled = False
        with self._client.messages.stream(
            model=self.model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for text in stream.text_stream:
                acc += text
                if on_delta:
                    on_delta(acc)
                if should_cancel and should_cancel():
                    cancelled = True
                    stream.close()
                    break
        if cancelled:
            # Annullato a metà: ritorna un oggetto vuoto (Analysis defaultato valido); il
            # chiamante rileva la cancellazione al confine-step e scarta comunque l'analisi.
            return {}
        return parse_json_lenient(acc)
