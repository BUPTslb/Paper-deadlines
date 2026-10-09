// Borrowed from https://github.com/moment/moment-timezone/issues/167
// Adds support for time zones 'UTC-12'..'UTC+12'
function addUtcTimeZones() {
  // Moment.js uses the IANA timezone database, which supports generic time zones like 'Etc/GMT+1'.
  // However, the signs for these time zones are inverted compared to ISO 8601.
  // For more details, see https://github.com/moment/moment-timezone/issues/167
  for (let offset = -12; offset <= 12; offset++) {
    const posixSign = offset <= 0 ? "+" : "-";
    const isoSign = offset >= 0 ? "+" : "-";
    const link = `Etc/GMT${posixSign}${Math.abs(
      offset
    )}|UTC${isoSign}${Math.abs(offset)}`;
    moment.tz.link(link);
  }
}

function update_filtering(data) {
  var page_url = "{{site.baseurl}}";
  store.set("{{site.domain}}-subs", data.subs);

  $(".confItem").hide();
  for (const j in data.all_subs) {
    const s = data.all_subs[j];
    const identifier = "." + s + "-conf";
    if (data.subs.includes(s)) {
      $(identifier).show();
    }
  }

  if (subs.length == 0) {
    window.history.pushState("", "", page_url);
  } else {
    window.history.pushState("", "", page_url + "/?sub=" + data.subs.join());
  }
}

// Urgency tier for a countdown: how far the deadline still is away.
// Returns a class name styled in deadlines.css (green > amber > orange > red,
// gray once the deadline has passed).
function countdownTier(remainingMs) {
  var hours = remainingMs / 3600000;
  if (hours <= 0) return "tier-past";
  if (hours <= 24 * 7) return "tier-week";
  if (hours <= 24 * 14) return "tier-2weeks";
  if (hours <= 24 * 30) return "tier-month";
  return "tier-far";
}

function applyCountdownTier($el, remainingMs) {
  $el
    .removeClass("tier-far tier-month tier-2weeks tier-week tier-past")
    .addClass(countdownTier(remainingMs));
}

function createCalendarFromObject(data) {
  return createCalendar({
    options: {
      class: "calendar-obj",

      // You can pass an ID. If you don't, one will be generated for you
      id: data.id,
    },
    data: {
      // Event title
      title: data.title,

      // Event start date
      start: data.date,

      // Event duration
      duration: 60,
    },
  });
}
