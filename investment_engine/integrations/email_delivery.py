from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage

from ..infrastructure.config import settings


class EmailDeliveryError(RuntimeError):
    pass


class AlertEmailSender:
    def __init__(self, configuration=settings):
        self.configuration = configuration

    @property
    def configured(self) -> bool:
        return bool(self.configuration.smtp_configured)

    def send(self, *, recipients: list[str], subject: str, text_body: str, html_body: str | None = None) -> None:
        clean = list(dict.fromkeys(str(item or "").strip().lower() for item in recipients if str(item or "").strip()))
        if not clean:
            raise EmailDeliveryError("alert_email_recipient_missing")
        if not self.configured:
            raise EmailDeliveryError("smtp_not_configured")
        message = EmailMessage()
        message["Subject"] = str(subject)[:240]
        message["From"] = f"{self.configuration.smtp_from_name} <{self.configuration.smtp_from_email}>"
        message["To"] = ", ".join(clean)
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")
        try:
            with smtplib.SMTP(self.configuration.smtp_host, self.configuration.smtp_port, timeout=25) as client:
                if self.configuration.smtp_starttls:
                    client.starttls()
                if self.configuration.smtp_username:
                    client.login(self.configuration.smtp_username, self.configuration.smtp_password)
                client.send_message(message)
        except Exception as exc:
            raise EmailDeliveryError(f"{type(exc).__name__}: {str(exc)[:300]}") from exc

    def send_alert(self, event: dict) -> None:
        labels = {
            "price_above": "Preço atingiu ou ultrapassou",
            "price_below": "Preço atingiu ou ficou abaixo de",
            "change_positive_pct": "Variação positiva atingiu",
            "change_negative_pct": "Variação negativa atingiu",
        }
        rules = event.get("triggered_rules") or []
        configured = event.get("configured_values") or {}
        observed = event.get("observed") or {}
        symbol = event.get("symbol") or "ATIVO"
        def formatted_condition(rule: str) -> str:
            value = configured.get(rule)
            suffix = "%" if "change_" in rule else ""
            sign = "-" if rule == "change_negative_pct" else ""
            return f"{labels.get(rule, rule)} {sign}{value}{suffix}"

        values = "; ".join(formatted_condition(rule) for rule in rules if configured.get(rule) is not None)
        subject = f"{symbol} ALERTA DE PREÇO - Formação do Investidor: {values or 'condição atingida'}"
        rule_text = "\n".join(f"- {formatted_condition(rule)}" for rule in rules)
        text_body = (
            f"O alerta configurado para {symbol} ({event.get('display_name') or symbol}) foi atingido.\n\n"
            f"Condição(ões):\n{rule_text}\n\n"
            f"Preço observado: {observed.get('price')}\n"
            f"Mínima do intervalo: {observed.get('low')}\n"
            f"Máxima do intervalo: {observed.get('high')}\n"
            f"Variação ante o fechamento anterior: {observed.get('change_pct')}%\n"
            f"Horário da cotação: {observed.get('quote_at')}\n"
            f"Fonte: {observed.get('source')}\n\n"
            "O alerta foi desativado automaticamente e permanece disponível no histórico. "
            "Cotações indicativas podem apresentar atraso e não substituem a confirmação na corretora."
        )
        safe = html.escape
        html_body = (
            "<h2>Alerta de preço atingido</h2>"
            f"<p><strong>{safe(symbol)}</strong> — {safe(str(event.get('display_name') or symbol))}</p>"
            f"<p>{safe('; '.join(formatted_condition(rule) for rule in rules))}</p>"
            f"<ul><li>Preço: {safe(str(observed.get('price')))}</li>"
            f"<li>Mínima: {safe(str(observed.get('low')))}</li>"
            f"<li>Máxima: {safe(str(observed.get('high')))}</li>"
            f"<li>Variação: {safe(str(observed.get('change_pct')))}%</li>"
            f"<li>Cotação: {safe(str(observed.get('quote_at')))}</li></ul>"
            "<p>O alerta foi desativado e transferido para o histórico.</p>"
            "<small>Cotação indicativa, possivelmente atrasada. Confirme na corretora.</small>"
        )
        self.send(recipients=event.get("recipients") or [], subject=subject, text_body=text_body, html_body=html_body)
