import en from "../../messages/en.json";
import hi from "../../messages/hi.json";
import ta from "../../messages/ta.json";
import type { Locale } from "./locale-context";

const ROOM_MESSAGES: Record<Locale, Record<string, string>> = {
  en: en.rooms as Record<string, string>,
  ta: ta.rooms as Record<string, string>,
  hi: hi.rooms as Record<string, string>,
};

export function getRoomName(roomType: string, locale: Locale): string {
  const rooms = ROOM_MESSAGES[locale] ?? ROOM_MESSAGES.en;
  return rooms[roomType] ?? roomType.replace(/_/g, " ");
}
