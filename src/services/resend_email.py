import logging
import requests
from typing import List
from datetime import datetime
from src.config.settings import RESEND_API_KEY, RESEND_SENDER, DEVELOPER_ALERT_EMAIL

logger = logging.getLogger(__name__)

class ResendEmailManager:
    """
    High-Performance, Premium Email Delivery Service using Resend.
    Sends beautifully formatted responsive HTML emails for daily digests and topic alerts.
    """

    def __init__(self):
        self.api_key = RESEND_API_KEY
        self.sender = RESEND_SENDER

    def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """Sends a robust, beautifully styled HTML email to a single recipient."""
        if not self.api_key:
            logger.warning("[Resend] API Key is missing. Email skipped.")
            return False

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": self.sender,
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }

        try:
            logger.info(f"[Resend] Dispatching email to {to_email} with subject: '{subject}'...")
            response = requests.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
                timeout=12
            )
            if response.status_code in [200, 201]:
                res_json = response.json()
                logger.info(f"[Resend] Success! Email sent to {to_email}. ID: {res_json.get('id')}")
                return True
            else:
                logger.error(f"[Resend] API returned error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.exception(f"[Resend] Exception raised during delivery to {to_email}: {e}")
            return False

    def build_daily_digest_html(self, articles: List, user_email: str) -> str:
        """
        Builds a gorgeous premium dark-themed HTML layout for the daily news digest.
        Features modern responsive design, elegant gradients, and clear typography.
        """
        article_cards_html = ""
        for index, art in enumerate(articles):
            bullets = ""
            if isinstance(art.summary_bullets, list):
                for bullet in art.summary_bullets:
                    bullets += f"<li style='margin-bottom: 6px; font-size: 14px; color: #cbd5e1;'>{bullet}</li>"
            else:
                bullets = f"<li style='margin-bottom: 6px; font-size: 14px; color: #cbd5e1;'>{art.why_it_matters or art.title}</li>"

            # Create tag pill
            tag_pill = f"<span style='display: inline-block; padding: 4px 10px; font-size: 11px; font-weight: 600; text-transform: uppercase; background: rgba(59, 130, 246, 0.15); color: #60a5fa; border-radius: 9999px; margin-bottom: 12px;'>{art.category or 'Global'}</span>"
            
            # Credibility element
            cred_score = int((art.credibility_score or 0.8) * 100)
            cred_color = "#34d399" if cred_score >= 70 else "#f59e0b"
            cred_html = f"<span style='font-size: 12px; font-weight: 600; color: {cred_color}; margin-left: 10px;'>⚡ {cred_score}% Credibility</span>"

            article_cards_html += f"""
            <div style='background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);'>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    {tag_pill}
                    {cred_html}
                </div>
                <h3 style='margin-top: 0; margin-bottom: 12px; font-size: 18px; font-weight: 700; color: #f8fafc; line-height: 1.4;'>{art.title}</h3>
                
                <p style='margin-top: 0; margin-bottom: 14px; font-size: 14px; font-style: italic; color: #94a3b8; border-left: 3px solid #3b82f6; padding-left: 10px;'>
                    <strong>Why it matters:</strong> {art.why_it_matters or 'Critical tactical signal.'}
                </p>

                <ul style='margin: 0; padding-left: 20px;'>
                    {bullets}
                </ul>

                <div style='margin-top: 18px; text-align: right;'>
                    <a href='{art.url}' target='_blank' style='display: inline-block; padding: 8px 16px; font-size: 13px; font-weight: 600; color: #ffffff; background: #3b82f6; border-radius: 6px; text-decoration: none; transition: background 0.2s;'>Read Full Analysis &rarr;</a>
                </div>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Daily Intelligence Briefing</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0; -webkit-font-smoothing: antialiased;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0f172a; padding: 30px 10px;">
                <tr>
                    <td align="center">
                        <table width="600" border="0" cellspacing="0" cellpadding="0" style="background: #111827; border: 1px solid #1f2937; border-radius: 16px; overflow: hidden; max-width: 600px; padding: 28px;">
                            
                            <!-- Header Logo & Subtitle -->
                            <tr>
                                <td align="center" style="padding-bottom: 30px; border-bottom: 1px solid #1f2937;">
                                    <h1 style="margin: 0 0 4px 0; font-size: 26px; font-weight: 800; letter-spacing: -0.025em; color: #ffffff; background: linear-gradient(to right, #60a5fa, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">UNIARC</h1>
                                    <p style="margin: 0; font-size: 13px; font-weight: 500; color: #64748b; letter-spacing: 0.05em; text-transform: uppercase;">Portal Intelligence Briefing</p>
                                </td>
                            </tr>

                            <!-- Body Text -->
                            <tr>
                                <td style="padding: 24px 0 16px 0;">
                                    <h2 style="margin-top: 0; font-size: 20px; font-weight: 700; color: #f8fafc;">Daily Intelligence Summary</h2>
                                    <p style="font-size: 15px; line-height: 1.6; color: #cbd5e1; margin-bottom: 20px;">
                                        Hello <strong>{user_email}</strong>,<br/>
                                        Here are the top strategic intelligence feeds compiled exclusively for you by the UniArc agent network.
                                    </p>
                                </td>
                            </tr>

                            <!-- Articles Container -->
                            <tr>
                                <td>
                                    {article_cards_html}
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td align="center" style="padding-top: 30px; border-top: 1px solid #1f2937; margin-top: 20px;">
                                    <p style="margin: 0; font-size: 12px; color: #475569;">
                                        This personalized intelligence briefing is delivered to you daily.
                                    </p>
                                    <p style="margin: 6px 0 0 0; font-size: 11px; color: #3b82f6; font-weight: 500;">
                                        UniArc Portal © 2026. All rights reserved.
                                    </p>
                                </td>
                            </tr>

                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    def build_topic_tracking_html(self, article, keywords: List[str], user_email: str) -> str:
        """
        Builds a beautiful premium HTML alert notifying a user when a newly ingested article matches
        one of their active 30-day topic subscription keywords.
        """
        bullets = ""
        if isinstance(article.summary_bullets, list):
            for bullet in article.summary_bullets:
                bullets += f"<li style='margin-bottom: 6px; font-size: 14px; color: #cbd5e1;'>{bullet}</li>"
        else:
            bullets = f"<li style='margin-bottom: 6px; font-size: 14px; color: #cbd5e1;'>{article.why_it_matters or article.title}</li>"

        keyword_pills = " ".join([f"<span style='display: inline-block; padding: 2px 8px; font-size: 11px; font-weight: 600; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 4px; margin-right: 6px; margin-bottom: 4px;'>#{kw}</span>" for kw in keywords])

        # Credibility & Impact Ratings
        cred_score = int((article.credibility_score or 0.8) * 100)
        impact_level = article.impact_score or 5

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Intelligence Alert: Matched Topic</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0; -webkit-font-smoothing: antialiased;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0f172a; padding: 30px 10px;">
                <tr>
                    <td align="center">
                        <table width="600" border="0" cellspacing="0" cellpadding="0" style="background: #111827; border: 1px solid #1f2937; border-radius: 16px; overflow: hidden; max-width: 600px; padding: 28px;">
                            
                            <!-- Header Logo & Subtitle -->
                            <tr>
                                <td align="center" style="padding-bottom: 24px; border-bottom: 1px solid #1f2937;">
                                    <div style="font-size: 28px; margin-bottom: 6px;">📡</div>
                                    <h1 style="margin: 0 0 4px 0; font-size: 22px; font-weight: 800; letter-spacing: -0.025em; color: #f8fafc;">IMMEDIATE TRACKING MATCH</h1>
                                    <p style="margin: 0; font-size: 12px; font-weight: 600; color: #10b981; letter-spacing: 0.05em; text-transform: uppercase;">UniArc Automated Agent Network</p>
                                </td>
                            </tr>

                            <!-- Body Text -->
                            <tr>
                                <td style="padding: 24px 0 16px 0;">
                                    <p style="font-size: 15px; line-height: 1.6; color: #cbd5e1; margin-bottom: 18px;">
                                        Hello <strong>{user_email}</strong>,<br/>
                                        Our ingestion systems have just categorized a new verified intelligence signal matching your tracked topic:
                                    </p>
                                    <div style="margin-bottom: 20px; padding: 10px; background: #1e293b; border-radius: 8px;">
                                        {keyword_pills}
                                    </div>
                                </td>
                            </tr>

                            <!-- Highlighted Article Card -->
                            <tr>
                                <td>
                                    <div style='background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);'>
                                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;'>
                                            <span style='display: inline-block; padding: 4px 10px; font-size: 11px; font-weight: 600; text-transform: uppercase; background: rgba(16, 185, 129, 0.15); color: #10b981; border-radius: 9999px;'>{article.category or 'Global'}</span>
                                            <span style='font-size: 12px; font-weight: 600; color: #3b82f6;'>✨ Impact Score: {impact_level}/10</span>
                                        </div>
                                        <h3 style='margin-top: 0; margin-bottom: 12px; font-size: 18px; font-weight: 700; color: #ffffff; line-height: 1.4;'>{article.title}</h3>
                                        
                                        <p style='margin-top: 0; margin-bottom: 14px; font-size: 14px; font-style: italic; color: #94a3b8; border-left: 3px solid #10b981; padding-left: 10px;'>
                                            <strong>Why it matters:</strong> {article.why_it_matters or 'Immediate matching context detected.'}
                                        </p>

                                        <ul style='margin: 0; padding-left: 20px;'>
                                            {bullets}
                                        </ul>

                                        <div style='margin-top: 18px; text-align: right;'>
                                            <a href='{article.url}' target='_blank' style='display: inline-block; padding: 8px 16px; font-size: 13px; font-weight: 600; color: #ffffff; background: #10b981; border-radius: 6px; text-decoration: none; transition: background 0.2s;'>Access Intelligence &rarr;</a>
                                        </div>
                                    </div>
                                </td>
                            </tr>

                            <!-- Sub-status Box -->
                            <tr>
                                <td style="padding-top: 24px;">
                                    <div style="background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.2); border-radius: 8px; padding: 12px; font-size: 13px; color: #60a5fa; line-height: 1.5;">
                                        ℹ️ You are subscribed to updates matching these keywords for 30 days. No duplicates will be sent.
                                    </div>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td align="center" style="padding-top: 24px; border-top: 1px solid #1f2937; margin-top: 24px;">
                                    <p style="margin: 0; font-size: 11px; color: #475569;">
                                        This alert was automatically dispatched based on active topic tracking rules.
                                    </p>
                                    <p style="margin: 4px 0 0 0; font-size: 11px; color: #10b981; font-weight: 500;">
                                        UniArc Portal © 2026. All rights reserved.
                                    </p>
                                </td>
                            </tr>

                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    def build_subscription_confirmation_html(self, keywords: List[str], user_email: str) -> str:
        """
        Builds a beautiful subscription confirmation email sent immediately when the user
        starts tracking a topic.
        """
        keyword_pills = " ".join([f"<span style='display: inline-block; padding: 4px 10px; font-size: 12px; font-weight: 600; background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 4px; margin-right: 6px; margin-bottom: 6px;'>#{kw}</span>" for kw in keywords])

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Topic Tracking Activated</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0; -webkit-font-smoothing: antialiased;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0f172a; padding: 30px 10px;">
                <tr>
                    <td align="center">
                        <table width="600" border="0" cellspacing="0" cellpadding="0" style="background: #111827; border: 1px solid #1f2937; border-radius: 16px; overflow: hidden; max-width: 600px; padding: 28px;">
                            
                            <!-- Header Logo -->
                            <tr>
                                <td align="center" style="padding-bottom: 24px; border-bottom: 1px solid #1f2937;">
                                    <div style="font-size: 32px; margin-bottom: 6px;">🛡️</div>
                                    <h1 style="margin: 0 0 4px 0; font-size: 22px; font-weight: 800; letter-spacing: -0.025em; color: #f8fafc;">TRACKING ACTIVATED</h1>
                                    <p style="margin: 0; font-size: 12px; font-weight: 600; color: #3b82f6; letter-spacing: 0.05em; text-transform: uppercase;">30-Day Intelligence Monitor</p>
                                </td>
                            </tr>

                            <!-- Body Text -->
                            <tr>
                                <td style="padding: 24px 0 16px 0;">
                                    <p style="font-size: 15px; line-height: 1.6; color: #cbd5e1; margin-bottom: 18px;">
                                        Hello <strong>{user_email}</strong>,<br/>
                                        You have successfully initiated tracking for the following topic keywords:
                                    </p>
                                    <div style="margin-bottom: 24px; padding: 14px; background: #1e293b; border-radius: 8px;">
                                        {keyword_pills}
                                    </div>
                                    <p style="font-size: 14px; line-height: 1.6; color: #94a3b8; margin-bottom: 24px;">
                                        For the next <strong>30 days</strong>, our background processors will monitor all newly verified world and educational news incoming from global agencies. The moment a matched signal is classified, you will receive an immediate premium email alert.
                                    </p>
                                </td>
                            </tr>

                            <!-- Confirm Box -->
                            <tr>
                                <td>
                                    <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 8px; padding: 14px; font-size: 13px; color: #10b981; line-height: 1.5; text-align: center;">
                                        ✓ Tracking setup complete. The monitoring system is active.
                                    </div>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td align="center" style="padding-top: 24px; border-top: 1px solid #1f2937; margin-top: 24px;">
                                    <p style="margin: 0; font-size: 11px; color: #475569;">
                                        You received this email because you clicked the "Track" button in the UniArc App.
                                    </p>
                                    <p style="margin: 4px 0 0 0; font-size: 11px; color: #3b82f6; font-weight: 500;">
                                        UniArc Portal © 2026. All rights reserved.
                                    </p>
                                </td>
                            </tr>

                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    def send_developer_error_alert(self, error_type: str, error_msg: str, traceback_str: str, context_details: str = None) -> bool:
        """
        Sends a premium, gorgeous dark-themed HTML alert to the development team
        (teamuniarc@yahoo.com) whenever an unhandled exception or crash occurs in production.
        """
        subject = f"🚨 UniArc Portal Crash Alert: {error_type}"
        # Build the HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>CRITICAL CRASH ALERT: {error_type}</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #090d16; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc; -webkit-font-smoothing: antialiased;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #090d16; padding: 40px 10px;">
                <tr>
                    <td align="center">
                        <table width="650" border="0" cellspacing="0" cellpadding="0" style="background: #111827; border: 2px solid #ef4444; border-radius: 16px; overflow: hidden; max-width: 650px; padding: 32px; box-shadow: 0 10px 15px -3px rgba(239, 68, 68, 0.2);">
                            
                            <!-- Header Crash Alert -->
                            <tr>
                                <td align="center" style="padding-bottom: 24px; border-bottom: 1px solid #1f2937;">
                                    <div style="font-size: 40px; margin-bottom: 10px;">🚨</div>
                                    <h1 style="margin: 0 0 4px 0; font-size: 24px; font-weight: 800; letter-spacing: -0.025em; color: #f8fafc; text-transform: uppercase;">PRODUCTION CRASH ALERT</h1>
                                    <p style="margin: 0; font-size: 13px; font-weight: 600; color: #ef4444; letter-spacing: 0.05em; text-transform: uppercase;">UniArc Portal Error Guard</p>
                                </td>
                            </tr>

                            <!-- Details Table -->
                            <tr>
                                <td style="padding: 24px 0 16px 0;">
                                    <h2 style="margin-top: 0; font-size: 18px; font-weight: 700; color: #f3f4f6;">Exception Metadatas</h2>
                                    <table width="100%" style="border-collapse: collapse; margin-bottom: 20px;">
                                        <tr style="border-bottom: 1px solid #1f2937;">
                                            <td style="padding: 10px 0; font-size: 14px; font-weight: 600; color: #9ca3af; width: 120px;">Type:</td>
                                            <td style="padding: 10px 0; font-size: 14px; font-weight: 700; color: #fca5a5;">{error_type}</td>
                                        </tr>
                                        <tr style="border-bottom: 1px solid #1f2937;">
                                            <td style="padding: 10px 0; font-size: 14px; font-weight: 600; color: #9ca3af;">Message:</td>
                                            <td style="padding: 10px 0; font-size: 14px; font-weight: 500; color: #fca5a5; font-family: monospace;">{error_msg}</td>
                                        </tr>
                                        <tr style="border-bottom: 1px solid #1f2937;">
                                            <td style="padding: 10px 0; font-size: 14px; font-weight: 600; color: #9ca3af;">Timestamp:</td>
                                            <td style="padding: 10px 0; font-size: 14px; color: #e5e7eb;">{datetime.utcnow().isoformat()} UTC</td>
                                        </tr>
                                        {f'''<tr style="border-bottom: 1px solid #1f2937;">
                                            <td style="padding: 10px 0; font-size: 14px; font-weight: 600; color: #9ca3af;">Context:</td>
                                            <td style="padding: 10px 0; font-size: 14px; color: #e5e7eb; font-family: monospace;">{context_details}</td>
                                        </tr>''' if context_details else ''}
                                    </table>
                                </td>
                            </tr>

                            <!-- Traceback -->
                            <tr>
                                <td>
                                    <h3 style="margin-top: 0; font-size: 16px; font-weight: 700; color: #f3f4f6;">Stack Traceback</h3>
                                    <div style="background: #090d16; border: 1px solid #ef4444; border-radius: 8px; padding: 18px; overflow-x: auto; font-family: 'Courier New', Courier, monospace; font-size: 12px; color: #fca5a5; line-height: 1.6; max-height: 400px; overflow-y: auto; text-align: left; white-space: pre-wrap;">{traceback_str}</div>
                                </td>
                            </tr>

                            <!-- Action Box -->
                            <tr>
                                <td style="padding-top: 24px;">
                                    <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 8px; padding: 14px; font-size: 13px; color: #f87171; line-height: 1.5; text-align: center;">
                                        ⚠️ Action Required: Please review the logs on Railway or Sentry to locate and resolve the regression immediately.
                                    </div>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td align="center" style="padding-top: 24px; border-top: 1px solid #1f2937; margin-top: 24px;">
                                    <p style="margin: 0; font-size: 11px; color: #4b5563;">
                                        Automated crash protection dispatched by the UniArc Portal Intelligence Agent.
                                    </p>
                                    <p style="margin: 4px 0 0 0; font-size: 11px; color: #ef4444; font-weight: 500;">
                                        UniArc Portal Security Guard © 2026.
                                    </p>
                                </td>
                            </tr>

                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(DEVELOPER_ALERT_EMAIL, subject, html_content)
