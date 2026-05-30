from typing import List
from agents.base_agent import TradingSignal, AgentVote
import os

MIN_CONSENSUS = float(os.getenv("MIN_CONSENSUS_SCORE", "0.65"))

# Umbral mínimo de veracity para que un catalizador influya en la decisión.
# Por debajo de esto, las noticias no modifican el score.
CATALYST_VERACITY_THRESHOLD = 0.75


class Decider:
    """
    Motor de votación ponderada entre agentes.

    Pesos actuales (6 agentes votantes + 1 gatekeeper):
      claude-sonnet  38% — decisión final, razonamiento macro + memoria histórica
      qwen-api       20% — Qwen3-235b, mejor benchmark math/quant del grupo
      deepseek-v3    18% — análisis quant/matemático especializado
      gpt-5.4-nano   14% — sentimiento macro, segunda opinión
      kronos-mini     5% — forecasting OHLCV cuantitativo (modelo local, probatorio)
      local-qwen      5% — gatekeeper local (voto de sanidad, sin costo API)

    Gemini 2.5 Flash: excluido del voting (free tier 20 req/día insuficiente para
    producción; puede usarse como fallback manual si otros agentes fallan)
    """

    # Pesos base. El orden define la jerarquía de herencia cuando un agente cae.
    AGENT_WEIGHTS = {
        "claude-sonnet": 0.38,
        "qwen-api":      0.20,
        "deepseek-v3":   0.18,
        "gpt-5.4-nano":  0.14,
        "kronos-mini":   0.05,
        "local-qwen":    0.05,
    }

    # Jerarquía descendente de confianza (primer disponible hereda el 50%)
    PRIORITY_ORDER = [
        "claude-sonnet",
        "qwen-api",
        "deepseek-v3",
        "gpt-5.4-nano",
        "local-qwen",
        "kronos-mini",
    ]

    def _effective_weights(self, present_ids: list[str]) -> dict[str, float]:
        """
        Redistribuye el peso de agentes ausentes:
          - 50% al siguiente mejor disponible en jerarquía
          - 50% distribuido proporcionalmente entre los demás presentes
        Los pesos resultantes suman siempre 1.0.
        """
        present = set(present_ids)
        weights = {aid: w for aid, w in self.AGENT_WEIGHTS.items() if aid in present}
        missing_weight = sum(
            w for aid, w in self.AGENT_WEIGHTS.items() if aid not in present
        )

        if missing_weight == 0 or not weights:
            return weights

        half = missing_weight / 2.0

        # 50% al primer disponible en jerarquía
        for aid in self.PRIORITY_ORDER:
            if aid in present:
                weights[aid] += half
                break

        # 50% restante proporcional al peso base de cada agente presente
        base_sum = sum(self.AGENT_WEIGHTS[aid] for aid in present)
        for aid in present:
            weights[aid] += half * (self.AGENT_WEIGHTS[aid] / base_sum)

        return weights

    @staticmethod
    def _base_id(agent_id: str) -> str:
        """Normaliza agent_id quitando sufijo de modelo, ej. 'qwen-api(qwen3-235b)' → 'qwen-api'."""
        return agent_id.split("(")[0]

    def decide(self, signals: List[TradingSignal], news_context: dict = None) -> dict:
        present_ids = [self._base_id(s.agent_id) for s in signals]
        weights     = self._effective_weights(present_ids)

        scores = {AgentVote.BUY: 0.0, AgentVote.SELL: 0.0, AgentVote.HOLD: 0.0}

        for signal in signals:
            weight = weights.get(self._base_id(signal.agent_id), 0.05)
            scores[signal.vote] += weight * signal.confidence

        # Los pesos efectivos ya suman 1.0 — no se normaliza

        winning_vote = max(scores, key=scores.get)
        winning_score = scores[winning_vote]

        # Las noticias solo influyen si se detectó un catalizador verificado
        # con veracity >= CATALYST_VERACITY_THRESHOLD.
        # Noticias rutinarias → multiplicador 1.0 (sin efecto).
        multiplier = 1.0
        if news_context:
            verified  = news_context.get("verified_catalyst", False)
            veracity  = float(news_context.get("catalyst_veracity", 0.0))
            direction = news_context.get("catalyst_direction", "NEUTRAL")
            avoid     = news_context.get("avoid_trading", False)

            if verified and veracity >= CATALYST_VERACITY_THRESHOLD:
                # Escalar el ajuste por veracity: a mayor certeza, mayor impacto.
                # veracity 0.75 → ajuste ±0.10 | veracity 1.0 → ajuste ±0.20
                strength = (veracity - 0.75) / 0.25 * 0.10 + 0.10  # rango [0.10, 0.20]

                if direction == "BULLISH":
                    # Catalizador positivo verificado: amplifica señales BUY, penaliza SELL
                    if winning_vote == AgentVote.BUY:
                        multiplier = 1.0 + strength        # e.g. 1.10 – 1.20
                    elif winning_vote == AgentVote.SELL:
                        multiplier = 1.0 - strength        # e.g. 0.80 – 0.90

                elif direction == "BEARISH":
                    # Catalizador negativo verificado: amplifica SELL, penaliza BUY
                    if winning_vote == AgentVote.SELL:
                        multiplier = 1.0 + strength
                    elif winning_vote == AgentVote.BUY:
                        multiplier = 1.0 - strength

            # avoid_trading es independiente del catalizador — para eventos extremos
            # (hack de exchange, ban gubernamental, etc.)
            if avoid and veracity >= CATALYST_VERACITY_THRESHOLD:
                multiplier *= 0.60

        winning_score_adjusted = winning_score * multiplier

        return {
            "decision": winning_vote.value if winning_score_adjusted >= MIN_CONSENSUS else "HOLD",
            "consensus_score": round(winning_score_adjusted, 4),
            "raw_score": round(winning_score, 4),
            "news_multiplier": round(multiplier, 3),
            "reached_consensus": winning_score_adjusted >= MIN_CONSENSUS,
            "votes": {v.value: round(s, 4) for v, s in scores.items()},
            "effective_weights": {aid: round(w, 4) for aid, w in weights.items()},
            "signals_count": len(signals),
            "agents_voted": [s.agent_id for s in signals],
            "news_sentiment": news_context.get("overall_sentiment", 0.0) if news_context else 0.0,
            "news_catalyst": news_context.get("catalyst_evidence", "") if news_context else "",
            "reasoning": [f"[{s.agent_id}] {s.vote.value} ({s.confidence:.2f}): {s.reasoning}" for s in signals],
        }
