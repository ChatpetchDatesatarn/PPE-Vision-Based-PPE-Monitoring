// All tunable constants. No IPs or hostnames here: every URL is relative to the page.
export const CONFIG = {
  MQTT_URL: () => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/mqtt`,
  TOPIC_PREFIX: "factory/safety/",
  STATUS_STALE_S: 15,        // <cam>/status เก่ากว่านี้ = Perception ล่ม
  CIRA_STALE_S: 30,          // cira/status เก่ากว่านี้ = Decision ล่ม
  RECENT_ALERTS_MAX: 50,
  EVENTS_PAGE_SIZE: 50,
  SUMMARY_REFRESH_S: 30,
  WEBRTC_RETRY_S: 5,
  SNAPSHOT_RETRY_MS: 1000,   // รูปอาจมาถึงช้ากว่า event เล็กน้อย
};

// localStorage keys (the only ones this app uses)
export const LS_KEYS = {
  SOUND: "safety.v3.sound",  // "on" | "off"
  GRID: "safety.v3.grid",    // "1" | "2" | "4"
  PAGE: "safety.v3.page",
};

export const NO_SNAPSHOT = "img/no-snapshot.svg";
