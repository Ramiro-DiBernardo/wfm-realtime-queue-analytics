/**
 * RTA tools for the RTA Queue Tracker (Google Sheets).
 *
 * Setup: import sheets/RTA_Queue_Tracker.xlsx into Google Sheets (File > Import > Replace spreadsheet),
 * then Extensions > Apps Script, paste this file, save, reload the sheet. A "RTA tools" menu appears.
 *
 * - Check queues now     logs every Red / Amber queue on the Live Board to the Alert Log tab
 * - Next interval        moves the board forward 15 minutes (rolls over to the next day) and checks queues
 * - Start replay         time-driven trigger: every minute, advance one interval and check queues,
 *                        so a past day can be "replayed" as if it were live
 * - Stop replay          removes the trigger
 */

const BOARD = 'Live Board';
const LOG = 'Alert Log';
const LISTS = 'Lists';
const FIRST_ROW = 7;        // first queue row on the board
const QUEUE_COUNT = 4;

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('RTA tools')
    .addItem('Check queues now', 'checkQueues')
    .addItem('Next interval', 'nextInterval')
    .addSeparator()
    .addItem('Start replay (1 interval per minute)', 'startReplay')
    .addItem('Stop replay', 'stopReplay')
    .addToUi();
}

/** Logs Red and Amber queues for the interval currently shown on the board. */
function checkQueues() {
  const ss = SpreadsheetApp.getActive();
  const board = ss.getSheetByName(BOARD);
  SpreadsheetApp.flush();                                   // make sure formulas are recalculated
  const date = board.getRange('B2').getDisplayValue();
  const time = board.getRange('B3').getDisplayValue();
  const rows = board.getRange(FIRST_ROW, 1, QUEUE_COUNT, 12).getValues();
  const log = ss.getSheetByName(LOG);
  const now = new Date();
  let alerts = 0;
  rows.forEach(function (r) {
    const queue = r[0], slNow = r[4], gap = r[9], status = r[10], lever = r[11];
    if (status === 'Red' || status === 'Amber') {
      log.appendRow([now, date + ' ' + time, queue, status, slNow, gap, lever]);
      alerts++;
    }
  });
  const last = log.getLastRow();
  if (last > 1) {
    log.getRange(2, 5, last - 1, 1).setNumberFormat('0%');
  }
  ss.toast(alerts ? alerts + ' queue(s) need attention at ' + time : 'All queues green at ' + time, 'RTA check', 5);
  return alerts;
}

/** Menu action: move 15 minutes forward and check the queues of the new interval. */
function nextInterval() {
  advanceInterval();
  checkQueues();
}

/** Moves the board 15 minutes forward, rolling over to the next date in the Lists tab. */
function advanceInterval() {
  const ss = SpreadsheetApp.getActive();
  const board = ss.getSheetByName(BOARD);
  const lists = ss.getSheetByName(LISTS);
  const times = lists.getRange('B2:B97').getDisplayValues().map(function (r) { return r[0]; });
  const dates = lists.getRange(2, 1, lists.getLastRow() - 1, 1).getDisplayValues().map(function (r) { return r[0]; });
  let t = times.indexOf(board.getRange('B3').getDisplayValue());
  let d = dates.indexOf(board.getRange('B2').getDisplayValue());
  t += 1;
  if (t >= times.length) {
    t = 0;
    d = Math.min(d + 1, dates.length - 1);
  }
  board.getRange('B2:B3').setNumberFormat('@');            // keep them as text so DATEVALUE/LEFT work
  board.getRange('B2').setValue(dates[d]);
  board.getRange('B3').setValue(times[t]);
}

/** Called by the replay trigger. */
function replayTick() {
  nextInterval();
}

function startReplay() {
  stopReplay();
  ScriptApp.newTrigger('replayTick').timeBased().everyMinutes(1).create();
  SpreadsheetApp.getActive().toast('Replay started: one interval per minute.', 'RTA tools', 5);
}

function stopReplay() {
  ScriptApp.getProjectTriggers().forEach(function (tr) {
    if (tr.getHandlerFunction() === 'replayTick') {
      ScriptApp.deleteTrigger(tr);
    }
  });
}
