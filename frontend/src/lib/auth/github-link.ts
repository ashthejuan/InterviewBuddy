import { AuthError, createOAuthUser, findUserByEmail, findUserByGithubId, setGithubId, type PublicUser } from "./users";

/**
 * Link a GitHub identity to our `users` row by github_id, else by verified email.
 * Never invents an email — caller must supply a real GitHub email.
 */
export async function linkOrCreateGithubUser(input: {
  githubId: string;
  email: string;
  name?: string | null;
}): Promise<PublicUser> {
  const email = input.email.trim().toLowerCase();
  if (!email || !email.includes("@")) {
    throw new AuthError(
      "EMAIL_REQUIRED",
      "GitHub did not provide an email — make your email visible or use password signup",
      400,
    );
  }
  if (!input.githubId.trim()) {
    throw new AuthError("GITHUB_ID_REQUIRED", "GitHub account id is required", 400);
  }

  const byGithub = await findUserByGithubId(input.githubId);
  if (byGithub) {
    return { id: byGithub.id, email: byGithub.email, name: byGithub.name };
  }

  const byEmail = await findUserByEmail(email);
  if (byEmail) {
    if (!byEmail.githubId) {
      await setGithubId(byEmail.id, input.githubId);
    } else if (byEmail.githubId !== input.githubId) {
      throw new AuthError(
        "GITHUB_CONFLICT",
        "This email is already linked to a different GitHub account",
        409,
      );
    }
    return { id: byEmail.id, email: byEmail.email, name: byEmail.name };
  }

  return createOAuthUser({
    email,
    name: input.name,
    githubId: input.githubId,
  });
}
