// How times are said to the patient ("tomorrow at 3:00 PM"), shared with the staff review cards

export function timeWords(date: Date) {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function whenWords(date: Date, now: Date, allDay = false) {
  const days = Math.round((startOfDay(date) - startOfDay(now)) / 86_400_000);
  const day =
    days === 0
      ? "today"
      : days === 1
        ? "tomorrow"
        : days < 7
          ? `on ${date.toLocaleDateString([], { weekday: "long" })}`
          : `on ${date.toLocaleDateString([], { month: "long", day: "numeric" })}`;
  // An all-day plan has no time to say
  return allDay ? day : `${day} at ${timeWords(date)}`;
}

export function startOfDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}
