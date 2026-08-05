import { cookies, headers } from "next/headers";
import OpenAI from "openai";
import { arcjetEnabled, rateLimitedClientWithBotDetection } from "@/lib/arcjet";
import { auth } from "@/lib/auth";
import { isLocale } from "@/lib/locale-context";

export const maxDuration = 30;

// Maps the app's locale cookie value to a Whisper ISO-639-1 language code.
// Pure + exported so the cookie-value → language-code mapping is unit
// testable without spinning up the route handler. "ta" and "hi" are both
// valid Whisper language codes (Tamil, Hindi); anything else (missing
// cookie, unknown/malformed value) safely falls back to "en" rather than
// throwing.
export function localeCookieToWhisperLanguage(cookieValue: string | undefined): string {
  return isLocale(cookieValue) ? cookieValue : "en";
}

// Whisper calls cost real money per request — cap sustained use per user and
// block non-browser clients outright (this route had no auth check at all
// before, so it was the one truly open cost-abuse surface in the app).
const aj = rateLimitedClientWithBotDetection({ refillRate: 5, interval: "1m", capacity: 10 });

export async function POST(req: Request) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (arcjetEnabled) {
    const decision = await aj.protect(req, { userId: session.user.id, requested: 1 });
    if (decision.isDenied()) {
      const status = decision.reason.isRateLimit() ? 429 : 403;
      return Response.json({ error: "Too many requests" }, { status });
    }
  }

  if (!process.env.OPENAI_API_KEY) {
    return Response.json({ error: "OPENAI_API_KEY not configured" }, { status: 503 });
  }

  const formData = await req.formData();
  const audio = formData.get("audio");

  if (!audio || !(audio instanceof File)) {
    return Response.json({ error: "No audio file provided" }, { status: 400 });
  }

  try {
    const client = new OpenAI();
    const cookieStore = await cookies();
    const language = localeCookieToWhisperLanguage(cookieStore.get("pf_locale")?.value);

    const result = await client.audio.transcriptions.create({
      model: "whisper-1",
      file: audio,
      language,
      prompt:
        "Indian residential floor plan, setback, FAR, BHK, vastu, staircase, bedroom, kitchen, toilet, plot, metres, feet",
    });

    const text = result.text?.trim();
    if (!text) {
      return Response.json({ error: "No speech detected" }, { status: 422 });
    }

    return Response.json({ text });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Transcription error";
    console.error("[transcribe]", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
