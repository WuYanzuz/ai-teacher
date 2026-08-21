// utils/util.js - small helpers
function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n) => (n < 10 ? "0" + n : "" + n);
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function mediaEmoji(t) {
  return { image: "📷", voice: "🎤", video: "🎬" }[t] || "📄";
}

module.exports = { formatTime, mediaEmoji };
