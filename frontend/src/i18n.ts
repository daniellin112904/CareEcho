// The patient screen in the patient's first language. Data (memory titles, names, family
// messages, reminder audio, the agent's captions) is shown as written, never translated here.

export type Lang = "en" | "es" | "zh";

/** Shown in the picker in their own language */
export const LANGUAGES: { code: Lang; name: string }[] = [
  { code: "en", name: "English" },
  { code: "es", name: "Español" },
  { code: "zh", name: "中文" },
];

export const LOCALES: Record<Lang, string> = { en: "en-US", es: "es-US", zh: "zh-CN" };

const LANGUAGE_KEY = "vela.language";

export function loadLanguage(): Lang {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    return LANGUAGES.some((l) => l.code === saved) ? (saved as Lang) : "en";
  } catch {
    return "en";
  }
}

export function saveLanguage(lang: Lang) {
  try {
    localStorage.setItem(LANGUAGE_KEY, lang);
  } catch {
    // Without storage the screen starts in English after a reload
  }
}

// Copies of FIRST_MESSAGE and LANGUAGE_PRESETS in backend/app/voice/agent.py: change both together.
// Sent as a first message override in case the language override doesn't apply the preset.
const FIRST_MESSAGES: Record<Lang, string> = {
  en: "Hi {{patient_name}}, it's Vela. What would you like to talk about?",
  es: "Hola {{patient_name}}, soy Vela. ¿De qué te gustaría hablar?",
  zh: "{{patient_name}}，你好，我是 Vela。你想聊些什么？",
};

export function firstMessage(lang: Lang, patientName: string) {
  return FIRST_MESSAGES[lang].replaceAll("{{patient_name}}", patientName);
}

type PartOfDay = "morning" | "afternoon" | "evening" | "night";

type Strings = {
  greeting: Record<Exclude<PartOfDay, "night">, string>;
  partOfDay: Record<PartOfDay, string>;
  /** The clock pill: "3:15 in the afternoon", "下午 3:15" */
  clockPill: (clock: string, part: string) => string;
  orb: { idle: string; connecting: string; listening: string; speaking: string; reminder: string };
  hint: { idle: string; connecting: string; listening: string };
  errorConnect: string;
  errorHearing: string;
  startTalking: string;
  stopTalking: string;
  language: string;
  comingUp: string;
  today: string;
  noPlans: string;
  notCertain: string;
  /** Spoken-style day words for whenWords */
  when: {
    today: string;
    tomorrow: string;
    weekday: (weekday: string) => string;
    date: (date: string) => string;
    /** "at 3:00 PM"; Spanish says "a la 1:00" but "a las 3:00" */
    at: (time: string, date: Date) => string;
    dayAt: (day: string, at: string) => string;
  };
  pickup: (who: string, at: string) => string;
  withWho: (who: string) => string;
  reminder: string;
  hearIt: string;
  hearAgain: string;
  ok: string;
  careToldTitle: string;
  careToldDetail: string;
  messageTitle: (from: string) => string;
  messageVoice: (from: string) => string;
  play: string;
  stop: string;
};

const spanishAt = (time: string, date: Date) => `${date.getHours() % 12 === 1 ? "a la" : "a las"} ${time}`;

export const STRINGS: Record<Lang, Strings> = {
  en: {
    greeting: { morning: "Good morning", afternoon: "Good afternoon", evening: "Good evening" },
    partOfDay: { morning: "in the morning", afternoon: "in the afternoon", evening: "in the evening", night: "at night" },
    clockPill: (clock, part) => `${clock} ${part}`,
    orb: { idle: "Talk to me", connecting: "One moment…", listening: "I'm listening", speaking: "Speaking…", reminder: "A reminder" },
    hint: { idle: "Tap the flame and ask me anything", connecting: "Getting ready to listen", listening: "Tap the flame when you're done" },
    errorConnect: "I can't connect right now. Tap the flame to try again.",
    errorHearing: "I'm having trouble hearing you. Tap the flame to try again.",
    startTalking: "Start talking",
    stopTalking: "Stop talking",
    language: "Language",
    comingUp: "Coming up",
    today: "Today",
    noPlans: "No plans yet today",
    notCertain: "Not certain yet",
    when: {
      today: "today",
      tomorrow: "tomorrow",
      weekday: (weekday) => `on ${weekday}`,
      date: (date) => `on ${date}`,
      at: (time) => `at ${time}`,
      dayAt: (day, at) => `${day} ${at}`,
    },
    pickup: (who, at) => `${who} picks you up ${at}`,
    withWho: (who) => `With ${who}`,
    reminder: "Reminder",
    hearIt: "Hear it",
    hearAgain: "Hear again",
    ok: "OK",
    careToldTitle: "Your care team has been told",
    careToldDetail: "Stay where you are if you can. You're not alone.",
    messageTitle: (from) => `Recorded message from ${from}`,
    messageVoice: (from) => `In ${from}'s own voice`,
    play: "Play",
    stop: "Stop",
  },
  es: {
    greeting: { morning: "Buenos días", afternoon: "Buenas tardes", evening: "Buenas noches" },
    partOfDay: { morning: "de la mañana", afternoon: "de la tarde", evening: "de la noche", night: "de la noche" },
    clockPill: (clock, part) => `${clock} ${part}`,
    orb: { idle: "Háblame", connecting: "Un momento…", listening: "Te escucho", speaking: "Hablando…", reminder: "Un recordatorio" },
    hint: {
      idle: "Toca la llama y pregúntame lo que quieras",
      connecting: "Preparándome para escucharte",
      listening: "Toca la llama cuando termines",
    },
    errorConnect: "No puedo conectarme ahora. Toca la llama para intentarlo de nuevo.",
    errorHearing: "Me cuesta oírte. Toca la llama para intentarlo de nuevo.",
    startTalking: "Empezar a hablar",
    stopTalking: "Dejar de hablar",
    language: "Idioma",
    comingUp: "Lo que sigue",
    today: "Hoy",
    noPlans: "Todavía no hay planes para hoy",
    notCertain: "Aún no es seguro",
    when: {
      today: "hoy",
      tomorrow: "mañana",
      weekday: (weekday) => `el ${weekday}`,
      date: (date) => `el ${date}`,
      at: spanishAt,
      dayAt: (day, at) => `${day} ${at}`,
    },
    pickup: (who, at) => `${who} pasa a buscarte ${at}`,
    withWho: (who) => `Con ${who}`,
    reminder: "Recordatorio",
    hearIt: "Escúchalo",
    hearAgain: "Escuchar otra vez",
    ok: "Entendido",
    careToldTitle: "Ya avisamos a tu equipo de cuidado",
    careToldDetail: "Quédate donde estás si puedes. Estoy aquí contigo.",
    messageTitle: (from) => `Mensaje grabado de ${from}`,
    messageVoice: (from) => `Con la voz de ${from}`,
    play: "Reproducir",
    stop: "Detener",
  },
  zh: {
    greeting: { morning: "早上好", afternoon: "下午好", evening: "晚上好" },
    partOfDay: { morning: "上午", afternoon: "下午", evening: "晚上", night: "夜里" },
    clockPill: (clock, part) => `${part} ${clock}`,
    orb: { idle: "和我说说话", connecting: "请稍等…", listening: "我在听", speaking: "正在说话…", reminder: "提醒" },
    hint: { idle: "点一下火焰，问我任何问题", connecting: "正在准备聆听", listening: "说完后点一下火焰" },
    errorConnect: "现在无法连接。请点一下火焰再试一次。",
    errorHearing: "我听不太清楚。请点一下火焰再试一次。",
    startTalking: "开始说话",
    stopTalking: "停止说话",
    language: "语言",
    comingUp: "接下来",
    today: "今天",
    noPlans: "今天还没有安排",
    notCertain: "还不确定",
    when: {
      today: "今天",
      tomorrow: "明天",
      weekday: (weekday) => weekday,
      date: (date) => date,
      at: (time) => time,
      dayAt: (day, at) => `${day}${at}`,
    },
    pickup: (who, at) => `${who}会在${at}来接你`,
    withWho: (who) => `和${who}一起`,
    reminder: "提醒",
    hearIt: "听一下",
    hearAgain: "再听一次",
    ok: "好的",
    careToldTitle: "已经通知你的护理团队了",
    careToldDetail: "如果可以，请待在原地。你不是一个人。",
    messageTitle: (from) => `${from}的录音留言`,
    messageVoice: (from) => `用${from}自己的声音`,
    play: "播放",
    stop: "停止",
  },
};

function partOfDay(date: Date): PartOfDay {
  const hour = date.getHours();
  return hour < 5 ? "night" : hour < 12 ? "morning" : hour < 17 ? "afternoon" : hour < 21 ? "evening" : "night";
}

export function greeting(lang: Lang, date: Date) {
  const part = partOfDay(date);
  return STRINGS[lang].greeting[part === "night" ? "evening" : part];
}

/** The top bar's clock: "3:15 in the afternoon", "3:15 de la tarde", "下午 3:15" */
export function clockPill(lang: Lang, date: Date) {
  const clock = `${date.getHours() % 12 || 12}:${String(date.getMinutes()).padStart(2, "0")}`;
  return STRINGS[lang].clockPill(clock, STRINGS[lang].partOfDay[partOfDay(date)]);
}

/** The big date line: "Tuesday, October 20", "Martes, 20 de octubre", "10月20日 星期二" */
export function dateLine(lang: Lang, date: Date) {
  const locale = LOCALES[lang];
  const weekday = date.toLocaleDateString(locale, { weekday: "long" });
  const day = date.toLocaleDateString(locale, { month: "long", day: "numeric" });
  if (lang === "zh") return `${day} ${weekday}`;
  return `${weekday[0].toUpperCase()}${weekday.slice(1)}, ${day}`;
}
