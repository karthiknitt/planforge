import OpenAI from "openai";

export const maxDuration = 30;

const openai = new OpenAI();

export async function POST(req: Request) {
  if (!process.env.OPENAI_API_KEY) {
    return Response.json({ error: "OPENAI_API_KEY not configured" }, { status: 503 });
  }

  const formData = await req.formData();
  const audio = formData.get("audio");

  if (!audio || !(audio instanceof File)) {
    return Response.json({ error: "No audio file provided" }, { status: 400 });
  }

  const transcription = await openai.audio.transcriptions.create({
    file: audio,
    model: "whisper-1",
    language: "en",
    // Domain hints help Whisper handle technical vocabulary correctly
    prompt:
      "Indian residential floor plan, setback, FAR, BHK, vastu, staircase, bedroom, kitchen, toilet, plot, metres, feet",
  });

  return Response.json({ text: transcription.text });
}
