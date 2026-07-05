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
     <p>Click the link below to log in to your Bargain Hunter portal. This link stays valid for 30 minutes.</p>
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
     <p>Your Bargain Hunter access has been approved. Click the link below to log in — it stays valid for 30 minutes.</p>
     <p><a href="${magicLinkUrl}" style="background:#ea580c;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">Log in to Bargain Hunter</a></p>
     <p>If you didn't request access, you can safely ignore this email.</p>`
  );
}

export async function sendAccessRequest(
  resendApiKey: string,
  ownerEmail: string,
  applicantEmail: string,
  adminUrl: string
): Promise<void> {
  await send(
    resendApiKey,
    ownerEmail,
    `Access request: ${applicantEmail}`,
    `<p>${applicantEmail} has requested access to Bargain Hunter.</p>
     <p>They've been added to the Subscribers DB with <b>Active = false</b>.</p>
     <p>Review and approve or reject them from the admin page:</p>
     <p><a href="${adminUrl}" style="background:#ea580c;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">Open admin</a></p>`
  );
}

export async function sendApplicantConfirmation(
  resendApiKey: string,
  to: string,
  dealsUrl: string,
  guidesUrl: string
): Promise<void> {
  await send(
    resendApiKey,
    to,
    "You're on the Bargain Hunter waitlist",
    `<p>Hi,</p>
     <p>Thanks for your interest in Bargain Hunter. You're on the list — access is invite-only, and
     we'll email you a login link as soon as you're approved.</p>
     <p>While you wait, you can browse the deals board and money-saving guides, no account needed:</p>
     <p>
       <a href="${dealsUrl}" style="background:#ea580c;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;margin-right:8px;">Browse deals</a>
       <a href="${guidesUrl}" style="background:#333;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">Read guides</a>
     </p>
     <p>If you didn't request access, you can safely ignore this email.</p>`
  );
}
