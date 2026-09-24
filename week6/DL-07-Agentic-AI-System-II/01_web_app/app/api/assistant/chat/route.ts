import { NextResponse } from "next/server";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface TripContextData {
  origin?: string;
  destination?: string;
  date?: string;
  time?: string;
  mode?: string;
  isDemo?: boolean;
  recommendation?: {
    actionCode?: string;
    riskLevel?: string;
    explanation?: {
      summary?: string;
      reasons?: string[];
      instructions?: string[];
    };
    weather?: {
      temperature?: number;
      precipitationMmH?: number;
      summary?: string;
    };
    transport?: {
      delayS?: number;
      hazard?: string;
    };
  };
}

function generateFallbackReply(userQuestion: string, context?: TripContextData) {
  const q = userQuestion.toLowerCase();
  const origin = context?.origin || "ต้นทาง";
  const destination = context?.destination || "ปลายทาง";
  const rec = context?.recommendation;
  const summary = rec?.explanation?.summary;
  const demoNotice = context?.isDemo ? "ข้อมูลทริปนี้เป็นตัวอย่าง ไม่ใช่ผลตรวจสอบจริง " : "";

  if (q.includes("ฝน") || q.includes("อากาศ") || q.includes("พายุ") || q.includes("สภาพอากาศ")) {
    if (rec?.weather?.summary) {
      return {
        reply: `${demoNotice}ข้อมูลสภาพอากาศที่มีสำหรับเส้นทาง ${origin} ➔ ${destination}: ${rec.weather.summary}${rec.weather.temperature != null ? ` อุณหภูมิ ${rec.weather.temperature}°C` : ""} กรุณาตรวจสอบประกาศล่าสุดก่อนเดินทางครับ`,
        proposal: null,
      };
    }
    return {
      reply: `${demoNotice}ยังไม่มีข้อมูลสภาพอากาศที่ตรวจสอบได้สำหรับเส้นทาง ${origin} ➔ ${destination} กรุณาตรวจสอบข้อมูลจากหน่วยงานทางการก่อนเดินทางครับ`,
      proposal: null,
    };
  }

  if (q.includes("รถติด") || q.includes("จราจร") || q.includes("ปิดถนน") || q.includes("น้ำท่วม") || q.includes("อุบัติเหตุ")) {
    if (rec?.transport?.hazard) {
      return {
        reply: `${demoNotice}ข้อมูลการเดินทางที่มีสำหรับเส้นทาง ${origin} ➔ ${destination}: ${rec.transport.hazard} กรุณาตรวจสอบสถานะล่าสุดก่อนออกเดินทางครับ`,
        proposal: null,
      };
    }
    return {
      reply: `${demoNotice}ยังไม่มีข้อมูลจราจรหรือการปิดถนนที่ตรวจสอบได้สำหรับเส้นทาง ${origin} ➔ ${destination} กรุณาตรวจสอบประกาศล่าสุดจากหน่วยงานที่เกี่ยวข้องครับ`,
      proposal: null,
    };
  }

  if (q.includes("เลื่อนเวลา") || q.includes("เปลี่ยนเวลา") || q.includes("กี่โมง") || q.includes("เวลา")) {
    return {
      reply: `${demoNotice}ระบุวันและเวลาที่ต้องการเปลี่ยนได้ครับ จากนั้นให้ระบบประเมินทริปใหม่ก่อนใช้ผลตัดสินใจ เพราะยังไม่มีหลักฐานพอที่จะแนะนำเวลาใหม่โดยอัตโนมัติ`,
      proposal: null,
    };
  }

  if (q.includes("ปลอดภัย") || q.includes("ไปได้ไหม") || q.includes("เดินทางได้ไหม") || q.includes("สรุป")) {
    if (!rec?.riskLevel || !rec.actionCode) {
      return {
        reply: `${demoNotice}ยังไม่มีผลประเมินความปลอดภัยที่ตรวจสอบได้สำหรับทริป ${origin} ➔ ${destination} กรุณาส่งคำขอประเมินและตรวจสอบประกาศล่าสุดก่อนตัดสินใจครับ`,
        proposal: null,
      };
    }
    const riskThai = rec.riskLevel === "HIGH" ? "ความเสี่ยงสูง" : rec.riskLevel === "MEDIUM" ? "ความเสี่ยงปานกลาง" : "ความเสี่ยงต่ำตามผลประเมิน";
    return {
      reply: `${demoNotice}ผลการประเมินทริป ${origin} ➔ ${destination}: ${riskThai}\n${summary || "กรุณาดูเหตุผลและข้อจำกัดในผลประเมิน พร้อมตรวจสอบข้อมูลล่าสุดก่อนเดินทางครับ"}`,
      proposal: null,
    };
  }

  return {
    reply: `${demoNotice}ผมช่วยอธิบายผลประเมินทริป ${origin} ไปยัง ${destination} และช่วยปรับแผนได้ครับ หากข้อมูลสดยังไม่พร้อม ผมจะแจ้งตามตรงแทนการคาดเดา`,
    proposal: null,
  };
}

export async function POST(req: Request) {
  try {
    const { messages, tripContext } = (await req.json()) as {
      messages: Message[];
      tripContext?: TripContextData;
    };

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
      return NextResponse.json({ error: "Missing messages" }, { status: 400 });
    }

    const apiKey = process.env.GEMINI_API_KEY || process.env.LLM_API_KEY;
    const userQuestion = messages[messages.length - 1].content;

    if (!apiKey) {
      return NextResponse.json(generateFallbackReply(userQuestion, tripContext));
    }

    const candidateModels = [
      process.env.LLM_MODEL_EXPLAINER,
      "gemini-2.5-flash-lite",
      "gemini-flash-latest",
      "gemini-3.5-flash-lite",
    ].filter(Boolean) as string[];

    const baseUrl = (process.env.GEMINI_API_BASE || "https://generativelanguage.googleapis.com/v1beta").replace(/\/$/, "");

    const systemPrompt = `คุณคือ "ผู้ช่วยเดินทางอัจฉริยะ (AI Travel Assistant)" ของระบบ Waypoint Safety Thailand
หน้าที่ของคุณคือ:
1. ตอบคำถามของผู้ใช้เกี่ยวกับการเดินทาง สภาพอากาศสด จราจรอุบัติเหตุ (Longdo Traffic) และการเตือนภัย ปภ.
2. สไตล์การตอบ: ภาษาไทยที่สุภาพ กระชับ สละสลวย ชัดเจน และเป็นมิตร
3. อิงข้อมูลจาก [บริบทการเดินทางปัจจุบัน] ที่ได้รับเท่านั้น หากไม่มีข้อมูลสภาพอากาศ/จราจร หรือได้รับข้อความแจ้งว่าบริการไม่พร้อมใช้งาน ให้ตอบตามตรงว่าไม่สามารถตรวจสอบข้อมูลได้เนื่องจากระบบภายนอกไม่พร้อมใช้งาน ห้ามกุข้อมูลตัวเลข อุณหภูมิ ปริมาณฝน หรือคาดเดาเอาเองว่าสภาพอากาศปกติเด็ดขาด
3.1 หาก isDemo เป็น true ต้องระบุชัดว่าข้อมูลเป็นตัวอย่างสำหรับการทดสอบระบบ ไม่ใช่ผลตรวจสอบจริงจากพื้นที่
4. หากผู้ใช้ต้องการปรับเปลี่ยนแผนการเดินทาง (เช่น "เลื่อนเวลาออกเดินทาง", "เปลี่ยนพาหนะ", "เปลี่ยนจุดหมาย"):
   - อธิบายเหตุผลในข้อความ "reply"
   - ให้ส่งข้อมูลใน "proposal" เป็น Object ที่มี "label" และ "changes" เพื่อให้หน้าเว็บนำไปอัปเดตฟอร์มได้
5. หากผู้ใช้เพียงถามคำถามทั่วไป ให้ใส่ "proposal": null
6. ตอบกลับเป็น JSON เท่านั้นตาม Schema นี้:
{
  "reply": "ข้อความตอบกลับภาษาไทย",
  "proposal": null หรือ {
    "label": "ข้อความสรุปการปรับเปลี่ยนสั้นๆ เช่น เลื่อนเวลาเป็น 15:30 น.",
    "changes": {
      "time": "HH:mm (ถ้าเปลี่ยนเวลา)",
      "date": "YYYY-MM-DD (ถ้าเปลี่ยนวัน)",
      "origin": "ชื่อสถานที่ (ถ้าเปลี่ยนต้นทาง)",
      "destination": "ชื่อสถานที่ (ถ้าเปลี่ยนปลายทาง)",
      "mode": "CAR | BUS | TRAIN | FLIGHT | FERRY | WALK | BICYCLE (ถ้าเปลี่ยนพาหนะ)"
    }
  }
}`;

    const contextText = tripContext ? JSON.stringify(tripContext, null, 2) : "ไม่มีข้อมูลทริปปัจจุบัน";

    const payload = {
      system_instruction: {
        parts: [{ text: systemPrompt }],
      },
      contents: [
        {
          role: "user",
          parts: [
            {
              text: `[บริบทการเดินทางปัจจุบัน]\n${contextText}\n\n[คำถาม/คำขอของผู้ใช้]\n${userQuestion}`,
            },
          ],
        },
      ],
      generationConfig: {
        temperature: 0.2,
        responseMimeType: "application/json",
      },
    };

    let candidateText: string | null = null;

    for (const m of candidateModels) {
      try {
        const url = `${baseUrl}/models/${m}:generateContent?key=${apiKey}`;
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (res.ok) {
          const data = await res.json();
          candidateText = data?.candidates?.[0]?.content?.parts?.[0]?.text ?? null;
          if (candidateText) {
            break;
          }
        } else {
          const errText = await res.text();
          console.warn(`Gemini model ${m} returned HTTP ${res.status}:`, errText);
        }
      } catch (err) {
        console.warn(`Gemini model ${m} request failed:`, err);
      }
    }

    if (!candidateText) {
      return NextResponse.json(generateFallbackReply(userQuestion, tripContext));
    }

    try {
      const parsed = JSON.parse(candidateText);
      return NextResponse.json(parsed);
    } catch {
      return NextResponse.json({
        reply: candidateText,
        proposal: null,
      });
    }
  } catch (error) {
    console.error("Assistant chat error:", error);
    return NextResponse.json({
      reply: "ขออภัยครับ ระบบกำลังประมวลผลข้อมูลการเดินทาง กรุณาลองใหม่อีกครั้งในสักครู่ครับ",
      proposal: null,
    });
  }
}
