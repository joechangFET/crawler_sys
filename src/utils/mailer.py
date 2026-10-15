"""Build an HTML crawl summary and send it with a CSV attachment via Gmail."""
import smtplib
from email.message import EmailMessage
from pathlib import Path
from collections import Counter
from logging import Logger

from src.model.page import PageResult


def _build_html_body(results: list[PageResult], site: str, duration: str) -> str:
    """Render the event count, duration and result-category distribution as HTML."""
    total = len(results)
    type_counter = Counter(r.event_type for r in results if r.event_type)

    rows = "".join(
        f"<tr><td>{event_type}</td><td>{count}</td></tr>"
        for event_type, count in sorted(type_counter.items(), key=lambda x: -x[1])
    )

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;">
      <h2>📊 {site.upper()} 爬蟲報表</h2>
      <table border="0" cellpadding="6" style="border-collapse:collapse;">
        <tr><td><b>爬取活動總數</b></td><td>{total} 筆</td></tr>
        <tr><td><b>總執行時間</b></td><td>{duration}</td></tr>
      </table>

      <h3 style="margin-top:24px;">活動類型分佈</h3>
      <table border="1" cellpadding="6" cellspacing="0"
             style="border-collapse:collapse;min-width:300px;">
        <thead style="background:#f0f0f0;">
          <tr><th>類型</th><th>數量</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>

      <p style="margin-top:24px;color:#888;font-size:12px;">
        詳細資料請見附件 CSV 檔案。
      </p>
    </body></html>
    """


def send_report_gmail(
    *,
    sender: str,
    app_password: str,
    receivers: list[str],
    subject: str,
    results: list[PageResult],
    site: str,
    duration: str,
    attachment_path: Path,
    logger: Logger,
) -> None:
    """
    Send crawl report via Gmail SMTP SSL.

    Args:
        sender:          Gmail address (e.g. yourname@gmail.com)
        app_password:    16-digit Google App Password
        receivers:       List of recipient email addresses
        subject:         Email subject line
        results:         List of PageResult from the crawl
        site:            Site name (e.g. "kktix")
        duration:        Human-readable duration string from CrawlMetrics
        attachment_path: Path to the CSV file to attach
        logger:          Logger instance for error reporting
    """
    try:
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = ", ".join(receivers)
        msg["Subject"] = subject

        # Plain text fallback
        msg.set_content(
            f"共爬取 {len(results)} 筆活動，執行時間 {duration}。\n"
            f"詳細資料請見附件 CSV 檔案。"
        )

        # HTML body
        html = _build_html_body(results, site, duration)
        msg.add_alternative(html, subtype="html")

        # CSV attachment
        if attachment_path.exists():
            data = attachment_path.read_bytes()
            msg.add_attachment(
                data,
                maintype="application",
                subtype="octet-stream",
                filename=attachment_path.name,
            )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, app_password)
            smtp.send_message(msg)

        logger.info(f"報表已寄送至 {', '.join(receivers)}")

    except Exception as e:
        logger.warning(f"郵件寄送失敗，不影響爬蟲結果：{e}")
