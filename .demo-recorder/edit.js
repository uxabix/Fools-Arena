const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const raw = path.join(__dirname, "raw");
const files = JSON.parse(fs.readFileSync(path.join(raw, "files.json"), "utf8"));
const extra = JSON.parse(fs.readFileSync(path.join(raw, "extra.json"), "utf8"));
const ffmpeg = "I:\\GreatProjects\\Durak\\presentation\\ffmpeg-src\\ffmpeg-master-latest-win64-gpl-shared\\bin\\ffmpeg.exe";
const out = "I:\\GreatProjects\\Durak\\presentation\\Fools-Arena-demo.mp4";
const SLOW = 1.28;
const BG = "0x12151c";
function fit(input, start, end, slow) {
  const speed = slow == null ? SLOW : slow;
  return "[" + input + ":v]trim=start=" + start + ":end=" + end + ",setpts=(PTS-STARTPTS)*" + speed;
}

const parts = [];

parts.push(
  fit(0, 0, 29.3) +
    ",scale=1280:720,setsar=1,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=" + BG +
    ",fps=25,tpad=start_mode=clone:start_duration=5[v0]"
);

parts.push(
  fit(0, 29.3, 44.79) + ",scale=1120:630,setsar=1[m]"
);
parts.push(
  fit(1, 29.3, 44.79) + ",scale=640:360,setsar=1[o]"
);
parts.push(
  fit(2, 29.3, 44.79) + ",scale=640:360,setsar=1[n]"
);
parts.push(
  "[m]pad=1920:1080:40:80:color=" + BG + "[bg]"
);
parts.push("[bg][o]overlay=1220:80[b1]");
parts.push("[b1][n]overlay=1220:500,fps=25,tpad=start_mode=clone:start_duration=4[v1]");

parts.push(
  fit(0, 44.79, 54.01) +
    ",scale=1280:720,setsar=1,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=" + BG +
    ",fps=25,tpad=start_mode=clone:start_duration=3[v2]"
);

parts.push(
  fit(1, 54.01, 59.2) +
    ",scale=1280:720,setsar=1,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=" + BG +
    ",fps=25,tpad=start_mode=clone:start_duration=2[v3]"
);

parts.push(
  fit(0, 59.2, 69.45) +
    ",scale=1280:720,setsar=1,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=" + BG +
    ",fps=25[v4]"
);

parts.push(
  "[3:v]setpts=PTS*" + SLOW +
    ",scale=460:996,setsar=1,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=" + BG +
    ",fps=25,tpad=start_mode=clone:start_duration=3[v5]"
);

parts.push(
  "[4:v]setpts=PTS*" + SLOW +
    ",scale=900:988,setsar=1,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=" + BG +
    ",fps=25,tpad=start_mode=clone:start_duration=2[v6]"
);

parts.push(
  fit(0, 80.77, 92.53) +
    ",scale=1280:720,setsar=1,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=" + BG +
    ",fps=25,tpad=start_mode=clone:start_duration=4[v7]"
);

parts.push(
  fit(2, 92.53, 97.4) +
    ",scale=1280:720,setsar=1,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=" + BG +
    ",fps=25,tpad=stop_mode=clone:stop_duration=3[v8]"
);

parts.push("[v0][v1][v2][v3][v4][v5][v6][v7][v8]concat=n=9:v=1:a=0[out]");

const script = parts.join(";\n");
const scriptPath = path.join(__dirname, "edit-filter.txt");
fs.writeFileSync(scriptPath, script);

const result = spawnSync(ffmpeg, [
  "-y",
  "-i", files.mira,
  "-i", files.oleg,
  "-i", files.nina,
  "-i", extra.phone,
  "-i", extra.tablet,
  "-filter_complex", script,
  "-map", "[out]",
  "-c:v", "libx264",
  "-pix_fmt", "yuv420p",
  "-crf", "20",
  "-preset", "veryfast",
  "-movflags", "+faststart",
  out,
], { stdio: "inherit" });

if (result.status !== 0) process.exit(result.status || 1);
