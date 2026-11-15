/**
 * Records three signed-in browsers through the main Fools Arena flows.
 * Timestamps in raw/marks.json are seconds from the shared start.
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8000";
const PASS = "DemoPass-36";
const LOBBY = "Evening table";
const ROOT = path.join(__dirname, "raw");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function loginFast(page, username) {
  await page.goto(BASE + "/accounts/login/", { waitUntil: "domcontentloaded" });
  await page.locator('[data-field="username"] input').fill(username);
  await page.locator('[data-field="password"] input').fill(PASS);
  await page.locator('button[type="submit"]').click({ noWaitAfter: true });
  await page.waitForURL(/\/fools\//, { timeout: 20000, waitUntil: "domcontentloaded" });
}

function beats(card, attack, trump) {
  if (!card || !attack) return false;
  const cardTrump = card.suit === trump;
  const attackTrump = attack.suit === trump;
  if (cardTrump && !attackTrump) return true;
  if (!cardTrump && attackTrump) return false;
  if (card.suit !== attack.suit) return false;
  return card.value > attack.value;
}

async function readState(page) {
  return page.evaluate(async () => {
    const id = location.pathname.split("/").filter(Boolean).pop();
    const response = await fetch("/api/fools/games/" + id + "/", { credentials: "same-origin" });
    if (!response.ok) return { status: "error", detail: response.status };
    return response.json();
  });
}

async function act(page) {
  if (!/\/play\//.test(page.url())) return "wait";
  const state = await readState(page);
  if (!state || state.status !== "in_progress") return state && state.status ? state.status : "wait";
  const me = (state.players || []).find((player) => Array.isArray(player.hand));
  if (!me) return "wait";
  const runtime = state.runtime || {};
  const trump = state.trump_card && state.trump_card.suit;
  const uid = String(me.user_id);
  const isAttacker = String(runtime.attacker_id) === uid;
  const isDefender = String(runtime.defender_id) === uid;
  const table = state.table || [];
  const open = table.filter((row) => row.attack && !row.defense);
  const wave = runtime.phase === "build" || runtime.phase === "defend";

  if (wave && isDefender && open.length) {
    for (const row of open) {
      const card = (me.hand || []).find((item) => beats(item, row.attack, trump));
      if (!card) continue;
      await page.locator('.play-card--hand[data-cid="' + card.id + '"]').click({ force: true });
      await sleep(450);
      await page.locator('.play-table-pair[data-table-card-id="' + row.id + '"]').click({ force: true });
      await sleep(2100);
      return "defend";
    }
    const take = page.locator("#btn-take");
    if (await take.isVisible() && await take.isEnabled()) {
      await take.click();
      await sleep(2200);
      return "take";
    }
  }

  if (runtime.phase === "between" && isAttacker && me.hand && me.hand.length) {
    const card = me.hand.slice().sort((a, b) => a.value - b.value)[0];
    await page.locator('.play-card--hand[data-cid="' + card.id + '"]').click({ force: true });
    await sleep(500);
    const attack = page.locator("#btn-attack");
    await attack.waitFor({ state: "visible", timeout: 4000 });
    await attack.click();
    await sleep(2100);
    return "attack";
  }

  if (wave && !isDefender && me.hand && me.hand.length) {
    const ranks = new Set();
    table.forEach((row) => {
      if (row.attack) ranks.add(row.attack.value);
      if (row.defense) ranks.add(row.defense.value);
    });
    const card = me.hand.find((item) => ranks.has(item.value));
    const attack = page.locator("#btn-attack");
    if (card && await attack.isVisible()) {
      await page.locator('.play-card--hand[data-cid="' + card.id + '"]').click({ force: true });
      await sleep(400);
      if (await attack.isEnabled()) {
        await attack.click();
        await sleep(2100);
        return "throw";
      }
    }
  }

  if (isAttacker && table.length && table.every((row) => row.defense)) {
    const bito = page.locator("#btn-bito");
    if (await bito.isVisible() && await bito.isEnabled()) {
      await bito.click();
      await sleep(2100);
      return "bito";
    }
  }

  const done = page.locator("#btn-done");
  if (await done.isVisible() && await done.isEnabled()) {
    await done.click();
    await sleep(1200);
    return "done";
  }
  return "wait";
}

async function main() {
  fs.rmSync(ROOT, { recursive: true, force: true });
  fs.mkdirSync(path.join(ROOT, "mira"), { recursive: true });
  fs.mkdirSync(path.join(ROOT, "oleg"), { recursive: true });
  fs.mkdirSync(path.join(ROOT, "nina"), { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const contextOptions = (name) => ({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: path.join(ROOT, name), size: { width: 1280, height: 720 } },
  });
  const miraContext = await browser.newContext(contextOptions("mira"));
  const olegContext = await browser.newContext(contextOptions("oleg"));
  const ninaContext = await browser.newContext(contextOptions("nina"));
  const mira = await miraContext.newPage();
  const oleg = await olegContext.newPage();
  const nina = await ninaContext.newPage();
  const t0 = Date.now();
  const marks = [];
  const mark = (name) => {
    const at = Math.round(((Date.now() - t0) / 1000) * 100) / 100;
    marks.push({ name, at });
    console.log("MARK", name, at);
  };

  try {
    mark("login");
    await Promise.all([
      (async () => {
        await mira.goto(BASE + "/accounts/login/", { waitUntil: "domcontentloaded" });
        await sleep(2200);
        await mira.getByRole("link", { name: "Create one" }).evaluate((el) => el.click());
        await mira.waitForURL(/register/, { timeout: 15000, waitUntil: "domcontentloaded" });
        await sleep(3200);
        await mira.evaluate(() => window.scrollTo(0, 320));
        await sleep(2200);
        await mira.goto(BASE + "/accounts/login/", { waitUntil: "domcontentloaded" });
        await sleep(500);
        const username = mira.locator('[data-field="username"] input');
        const password = mira.locator('[data-field="password"] input');
        await username.click();
        await username.pressSequentially("mira", { delay: 120 });
        await password.click();
        await password.pressSequentially(PASS, { delay: 45 });
        await sleep(500);
        const typed = await username.inputValue();
        if (typed !== "mira") await username.fill("mira");
        if ((await password.inputValue()) !== PASS) await password.fill(PASS);
        await mira.locator('button[type="submit"]').click({ noWaitAfter: true });
        await mira.waitForURL(/\/fools\//, { timeout: 20000, waitUntil: "domcontentloaded" });
      })(),
      loginFast(oleg, "oleg"),
      loginFast(nina, "nina"),
    ]);

    mark("lobbies");
    await mira.locator("#lobby-search").pressSequentially("no-such-lobby", { delay: 70 });
    await sleep(1800);
    await mira.locator("#lobby-clear-filters").click();
    await sleep(500);
    await mira.locator("#lobby-sort").selectOption("seats");
    await sleep(700);
    await mira.locator("#lobby-deck").selectOption("36");
    await sleep(700);
    await mira.locator("#lobby-open-seats").check();
    await sleep(1200);
    await mira.locator("#lobby-transfer").check();
    await sleep(1200);
    await mira.locator("#lobby-clear-filters").click();
    await sleep(600);

    mark("create");
    await mira.locator("#create-open").click();
    await mira.locator("#id_name").pressSequentially(LOBBY, { delay: 70 });
    await mira.locator("#id_max_players").fill("3");
    await mira.locator("#id_card_count").selectOption("36");
    await mira.locator("#id_is_private").check();
    await sleep(1600);
    await mira.locator("#id_password").fill("table-pass");
    await sleep(1400);
    await mira.locator("#id_is_private").uncheck();
    await mira.locator("summary").filter({ hasText: "More rules" }).click();
    await sleep(700);
    await mira.locator("#id_is_transferable").check();
    await sleep(400);
    await mira.locator("#id_share_hand_signals").check();
    await sleep(500);
    await mira.locator("#create-submit").click({ noWaitAfter: true });
    await mira.waitForURL(/\/fools\/lobbies\//, { timeout: 20000, waitUntil: "domcontentloaded" });
    await sleep(2200);
    const lobbyUrl = mira.url();
    await mira.locator("#btn-settings").click();
    await sleep(2400);
    await mira.locator("#settings-cancel").click();
    await sleep(500);

    mark("split");
    await oleg.locator("#lobby-search").fill(LOBBY);
    await oleg.locator(".lobby-join").first().waitFor({ state: "visible", timeout: 8000 });
    await sleep(700);
    await oleg.locator(".lobby-join").first().evaluate((el) => el.click());
    await oleg.waitForURL(/\/fools\/lobbies\//, { timeout: 15000, waitUntil: "domcontentloaded" });
    await sleep(700);
    await nina.locator("#lobby-search").fill("Evening");
    await sleep(600);
    await nina.locator("#lobby-deck").selectOption("36");
    await sleep(500);
    await nina.locator(".lobby-join").first().waitFor({ state: "visible", timeout: 8000 });
    await nina.locator(".lobby-join").first().evaluate((el) => el.click());
    await nina.waitForURL(/\/fools\/lobbies\//, { timeout: 15000, waitUntil: "domcontentloaded" });
    await sleep(900);

    await mira.locator("#chat-input").waitFor({ state: "visible", timeout: 10000 });
    await mira.locator("#chat-input").fill("Ready when you are.");
    await mira.locator("#chat-send").click();
    await sleep(1400);
    await oleg.locator("#chat-input").fill("I am in.");
    await oleg.locator("#chat-send").click();
    await sleep(1400);
    await nina.locator("#chat-input").fill("Deal us in.");
    await nina.locator("#chat-send").click();
    await sleep(2000);

    for (const page of [oleg, nina, mira]) {
      await page.locator("#btn-ready").click();
      await sleep(700);
    }
    await mira.waitForFunction(() => {
      const button = document.getElementById("btn-start");
      return button && button.getAttribute("aria-disabled") === "false";
    }, { timeout: 10000 });
    await sleep(600);
    await mira.locator("#btn-start").click({ noWaitAfter: true });
    await mira.waitForURL(/\/play\//, { timeout: 20000, waitUntil: "domcontentloaded" });
    await oleg.waitForURL(/\/play\//, { timeout: 20000, waitUntil: "domcontentloaded" });
    await nina.waitForURL(/\/play\//, { timeout: 20000, waitUntil: "domcontentloaded" });
    await mira.locator(".play-card--hand").first().waitFor({ state: "visible", timeout: 15000 });
    await sleep(2800);

    mark("game");
    const gameStart = Date.now();
    let actions = 0;
    let sorted = false;
    let chatted = false;
    let olegShown = false;
    while (Date.now() - gameStart < 46000 && actions < 8) {
      let progressed = false;
      for (const page of [mira, oleg, nina]) {
        const who = page === mira ? "mira" : page === oleg ? "oleg" : "nina";
        let result = "wait";
        try {
          result = await act(page);
        } catch (error) {
          console.log("act-error", who, error.message);
        }
        if (result && result !== "wait" && result !== "in_progress" && result !== "finished" && result !== "error") {
          actions += 1;
          progressed = true;
          console.log("action", who, result, actions);
          if (!olegShown && who === "oleg") {
            mark("oleg-view");
            olegShown = true;
          }
          break;
        }
      }
      if (!sorted && actions >= 1) {
        await mira.locator("#btn-sort").click().catch(() => {});
        sorted = true;
        await sleep(900);
      }
      if (!chatted && actions >= 2) {
        await mira.locator("#play-chat-toggle").click().catch(() => {});
        await sleep(400);
        const input = mira.locator("#play-chat-input");
        if (await input.isVisible().catch(() => false)) {
          await input.fill("Good luck.");
          await mira.locator("#play-chat-form button[type=submit]").click();
          await sleep(700);
          await oleg.locator("#play-chat-toggle").click().catch(() => {});
          const olegInput = oleg.locator("#play-chat-input");
          if (await olegInput.isVisible().catch(() => false)) {
            await olegInput.fill("Watch the trump.");
            await oleg.locator("#play-chat-form button[type=submit]").click();
          }
          chatted = true;
          await sleep(1000);
        }
      }
      if (!progressed) await sleep(350);
    }

    mark("responsive");
    const playUrl = mira.url();
    const phoneDir = path.join(ROOT, "phone");
    const tabletDir = path.join(ROOT, "tablet");
    fs.mkdirSync(phoneDir, { recursive: true });
    fs.mkdirSync(tabletDir, { recursive: true });
    const storage = await miraContext.storageState();
    const phoneContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
      recordVideo: { dir: phoneDir, size: { width: 390, height: 844 } },
      storageState: storage,
    });
    const phone = await phoneContext.newPage();
    await phone.goto(playUrl, { waitUntil: "domcontentloaded" });
    await phone.locator(".play-card--hand").first().waitFor({ state: "visible", timeout: 15000 }).catch(() => {});
    await sleep(2800);
    const nav = phone.locator("#site-nav-toggle");
    if (await nav.isVisible()) await nav.click();
    await sleep(2600);
    if (await nav.isVisible()) await nav.click();
    await sleep(1200);
    const phoneVideo = phone.video();
    await phoneContext.close();
    const phonePath = await phoneVideo.path();

    const tabletContext = await browser.newContext({
      viewport: { width: 820, height: 900 },
      recordVideo: { dir: tabletDir, size: { width: 820, height: 900 } },
      storageState: storage,
    });
    const tablet = await tabletContext.newPage();
    const tabletVideo = tablet.video();
    await tablet.goto(BASE + "/fools/", { waitUntil: "domcontentloaded" });
    await sleep(2200);
    await tablet.locator("#lobby-search").fill("Evening");
    await sleep(1800);
    await tabletContext.close();
    const tabletPath = await tabletVideo.path();
    fs.writeFileSync(path.join(ROOT, "extra.json"), JSON.stringify({ phone: phonePath, tablet: tabletPath }, null, 2));

    mark("profile");
    await mira.goto(BASE + "/accounts/profile/", { waitUntil: "domcontentloaded" });
    await sleep(3200);
    await mira.evaluate(() => window.scrollTo(0, 460));
    await sleep(2200);
    await mira.goto(BASE + "/accounts/players/oleg/", { waitUntil: "domcontentloaded" });
    await sleep(2600);

    mark("dm");
    await mira.goto(BASE + "/chat/direct/new/", { waitUntil: "domcontentloaded" });
    await mira.locator('input[name="other_username"]').pressSequentially("nina", { delay: 90 });
    await sleep(400);
    await mira.locator('button[type="submit"]').click({ noWaitAfter: true });
    await mira.waitForURL(/\/chat\//, { timeout: 15000, waitUntil: "domcontentloaded" });
    await sleep(500);
    await mira.locator("#chat-input").fill("See you at the next table.");
    await mira.locator("#chat-send").click();
    await sleep(2200);

    mark("nina-inbox");
    await nina.goto(BASE + "/chat/", { waitUntil: "domcontentloaded" });
    await sleep(1400);
    await nina.locator(".chat-inbox-list a").first().click({ noWaitAfter: true });
    await nina.waitForURL(/\/chat\/[0-9a-f-]{8,}/, { timeout: 15000, waitUntil: "domcontentloaded" });
    await sleep(800);
    await nina.locator("#chat-input").fill("I will be there.");
    await nina.locator("#chat-send").click();
    await sleep(2600);
    mark("end");
    console.log("lobby", lobbyUrl);
  } catch (error) {
    console.error(error);
    await mira.screenshot({ path: path.join(ROOT, "fail-mira.png") }).catch(() => {});
    await oleg.screenshot({ path: path.join(ROOT, "fail-oleg.png") }).catch(() => {});
    await nina.screenshot({ path: path.join(ROOT, "fail-nina.png") }).catch(() => {});
    mark("end");
    fs.writeFileSync(path.join(ROOT, "marks.json"), JSON.stringify(marks, null, 2));
    throw error;
  } finally {
    const miraVideo = mira.video();
    const olegVideo = oleg.video();
    const ninaVideo = nina.video();
    await miraContext.close();
    await olegContext.close();
    await ninaContext.close();
    await browser.close();
    const files = {
      mira: await miraVideo.path(),
      oleg: await olegVideo.path(),
      nina: await ninaVideo.path(),
    };
    fs.writeFileSync(path.join(ROOT, "files.json"), JSON.stringify(files, null, 2));
    fs.writeFileSync(path.join(ROOT, "marks.json"), JSON.stringify(marks, null, 2));
    console.log(files);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
