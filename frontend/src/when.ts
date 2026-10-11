// How times are said to the patient ("tomorrow at 3:00 PM"), shared with the staff review cards.
// Staff pages call these without a language and keep the English output they always had.

import { LOCALES, STRINGS, type Lang } from "./i18n";

// English keeps the browser's own locale, as before; the patient's other languages use theirs
const locale = (lang: Lang) => (lang === "en" ? [] : LOCALES[lang]);

export function timeWords(date: Date, lang: Lang = "en") {
  // hour12: zh-CN would say 15:00; the patient screen says 下午3:00
  return date.toLocaleTimeString(locale(lang), { hour: "numeric", minute: "2-digit", ...(lang === "zh" && { hour12: true }) });
}

/** "at 3:00 PM", "a las 3:00 p. m.", "下午3:00" */
export function atTimeWords(date: Date, lang: Lang = "en") {
  return STRINGS[lang].when.at(timeWords(date, lang), date);
}

export function whenWords(date: Date, now: Date, allDay = false, lang: Lang = "en") {
  const words = STRINGS[lang].when;
  const days = Math.round((startOfDay(date) - startOfDay(now)) / 86_400_000);
  const day =
    days === 0
      ? words.today
      : days === 1
        ? words.tomorrow
        : days < 7
          ? words.weekday(date.toLocaleDateString(locale(lang), { weekday: "long" }))
          : words.date(date.toLocaleDateString(locale(lang), { month: "long", day: "numeric" }));
  // An all-day plan has no time to say
  return allDay ? day : words.dayAt(day, atTimeWords(date, lang));
}

export function startOfDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}
