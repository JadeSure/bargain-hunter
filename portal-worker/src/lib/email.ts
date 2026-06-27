async function send(
  resendApiKey: string,
  to: string,
  subject: string,
  html: string
): Promise<void> {
  const resp = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${resendApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: "Bargain Hunter <onboarding@resend.dev>",
      to: [to],
      subject,
      html,
    }),
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Resend failed: ${resp.status} ${body}`);
  }
}

export async function sendMagicLink(
  resendApiKey: string,
  to: string,
  magicLinkUrl: string
): Promise<void> {
  await send(
    resendApiKey,
    to,
    "Your Bargain Hunter login link",
    `<p>Hi,</p>
     <p>Click the link below to log in to your Bargain Hunter portal. This link expires in 15 minutes.</p>
     <p><a href="${magicLinkUrl}" style="background:#ea580c;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">Log in to Bargain Hunter</a></p>
     <p>If you didn't request this, you can safely ignore this email.</p>`
  );
}

export async function sendAccessRequest(
  resendApiKey: string,
  ownerEmail: string,
  applicantEmail: string
): Promise<void> {
  await send(
    resendApiKey,
    ownerEmail,
    `Access request: ${applicantEmail}`,
    `<p>${applicantEmail} has requested access to Bargain Hunter.</p>
     <p>They've been added to the Waitlist (Notion) with status <b>pending</b>.</p>
     <p>To approve, add them to the Notion Subscribers DB and set Active = true.</p>
     <p>They can then log in at <a href="https://bargainhunter.app/login">bargainhunter.app/login</a> with their email.</p>`
  );
}
