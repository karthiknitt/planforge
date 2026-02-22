import OpenAI from "openai";

export const maxDuration = 30;

export async function POST(req: Request) {
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

    const result = await client.audio.transcriptions.create({
      model: "whisper-1",
      file: audio,
      language: "en",
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
