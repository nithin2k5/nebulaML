/**
 * NebulaML Email Templates
 *
 * These HTML templates are designed to match the premium dark theme of the website.
 * Theme tokens used:
 * - Background: #09090b (Zinc-950)
 * - Card: #101013
 * - Primary: #6b4eff (Indigo-400)
 * - Foreground/Text: #fafafa
 * - Muted: #a1a1aa (Zinc-400)
 * - Border: #27272a (Zinc-800)
 */

export const generateConfirmationEmail = (userName) => `
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Inquiry Received - NebulaML</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background-color: #09090b;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #fafafa;
            line-height: 1.6;
        }
        .container {
            width: 100%;
            max-width: 600px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        .card {
            background-color: #101013;
            border: 1px solid #27272a;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            text-align: center;
        }
        .logo {
            font-size: 28px;
            font-weight: 800;
            color: #fafafa;
            margin-bottom: 24px;
            letter-spacing: -0.05em;
        }
        .logo-accent {
            color: #6b4eff;
        }
        .greeting {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 16px;
            color: #fafafa;
        }
        .message {
            font-size: 16px;
            color: #a1a1aa;
            margin-bottom: 32px;
        }
        .button {
            display: inline-block;
            background-color: #6b4eff;
            color: #ffffff;
            font-weight: 600;
            text-decoration: none;
            padding: 14px 28px;
            border-radius: 8px;
            margin-bottom: 32px;
            transition: opacity 0.2s;
        }
        .divider {
            height: 1px;
            background-color: #27272a;
            margin: 32px 0;
        }
        .footer {
            font-size: 14px;
            color: #a1a1aa;
        }
        .footer a {
            color: #6b4eff;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo">Nebula<span class="logo-accent">ML</span></div>
            
            <div class="greeting">Hi ${userName},</div>
            
            <div class="message">
                Thanks for reaching out! We've received your message and our team is currently reviewing it. <br><br>
                We usually respond within 24-48 hours. In the meantime, feel free to explore our platform.
            </div>
            
            <a href="https://nebulaml.com/dashboard" class="action-button button">Go to Dashboard</a>
            
            <div class="divider"></div>
            
            <div class="footer">
                &copy; ${new Date().getFullYear()} NebulaML. All rights reserved.<br>
                If you have any urgent questions, simply reply to this email.
            </div>
        </div>
    </div>
</body>
</html>
`;

export const generateInquiryEmail = (userName, userEmail, message) => `
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Contact Inquiry - NebulaML</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background-color: #09090b;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #fafafa;
            line-height: 1.6;
        }
        .container {
            width: 100%;
            max-width: 600px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        .card {
            background-color: #101013;
            border: 1px solid #27272a;
            border-radius: 12px;
            padding: 40px;
        }
        .logo {
            font-size: 24px;
            font-weight: 800;
            color: #fafafa;
            margin-bottom: 32px;
            border-bottom: 1px solid #27272a;
            padding-bottom: 24px;
        }
        .logo-accent {
            color: #6b4eff;
        }
        .header {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 24px;
            color: #6b4eff;
        }
        .detail-row {
            margin-bottom: 16px;
        }
        .detail-label {
            font-size: 14px;
            color: #a1a1aa;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 4px;
        }
        .detail-value {
            font-size: 16px;
            color: #fafafa;
            background-color: #09090b;
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #27272a;
        }
        .message-box {
            font-size: 16px;
            color: #fafafa;
            background-color: #09090b;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #27272a;
            white-space: pre-wrap;
            margin-bottom: 32px;
        }
        .footer {
            font-size: 14px;
            color: #a1a1aa;
            text-align: center;
            margin-top: 32px;
            border-top: 1px solid #27272a;
            padding-top: 24px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo">Nebula<span class="logo-accent">ML</span> <span style="font-size: 14px; color: #a1a1aa; font-weight: 400; margin-left: 8px;">Admin Alert</span></div>
            
            <div class="header">New Contact Form Submission</div>
            
            <div class="detail-row">
                <div class="detail-label">Name</div>
                <div class="detail-value">${userName}</div>
            </div>
            
            <div class="detail-row">
                <div class="detail-label">Email Address</div>
                <div class="detail-value">
                    <a href="mailto:${userEmail}" style="color: #6b4eff; text-decoration: none;">${userEmail}</a>
                </div>
            </div>
            
            <div class="detail-row">
                <div class="detail-label">Message</div>
                <div class="message-box">${message.replace(/\n/g, '<br>')}</div>
            </div>
            
            <div class="footer">
                This is an automated message from the NebulaML website contact form.
            </div>
        </div>
    </div>
</body>
</html>
`;
