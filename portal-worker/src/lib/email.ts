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
      from: "Bargain Hunter <noreply-bargain-hunter@sylvalume.online>",
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
     <p>Click the link below to log in to your Bargain Hunter portal. This link stays valid for 8 hours.</p>
     <p><a href="${magicLinkUrl}" style="background:#ea580c;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">Log in to Bargain Hunter</a></p>
     <p>If you didn't request this, you can safely ignore this email.</p>`
  );
}

export async function sendActivationEmail(
  resendApiKey: string,
  to: string,
  magicLinkUrl: string
): Promise<void> {
  await send(
    resendApiKey,
    to,
    "You've been approved — log in to Bargain Hunter",
    `<p>Hi,</p>
     <p>Your Bargain Hunter access has been approved. Click the link below to log in — it stays valid for 8 hours.</p>
     <p><a href="${magicLinkUrl}" style="background:#ea580c;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">Log in to Bargain Hunter</a></p>
     <p>If you didn't request access, you can safely ignore this email.</p>`
  );
}

export async function sendAccessRequest(
  resendApiKey: string,
  ownerEmail: string,
  applicantEmail: string,
  loginUrl: string
): Promise<void> {
  await send(
    resendApiKey,
    ownerEmail,
    `Access request: ${applicantEmail}`,
    `<p>${applicantEmail} has requested access to Bargain Hunter.</p>
     <p>They've been added to the Subscribers DB with <b>Active = false</b>.</p>
     <p>To approve and send them a login link, call:</p>
     <pre style="background:#f4f4f4;padding:12px;border-radius:4px;">POST /auth/request-access/approve\n{"email":"${applicantEmail}"}</pre>
     <p>Or log in to your portal and use the admin UI at <a href="${loginUrl}">${loginUrl}</a>.</p>`
  );
}
