/**
 * Maverickframe HR Bridge Google Apps Script
 * - Stores OAuth tokens persistently in Script Properties
 * - Saves selected candidates to the Candidates sheet
 */
function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  return jsonResponse({ ok: true, service: 'Maverickframe HR token store and candidate database' });
}

function doPost(e) {
  try {
    var body = {};
    if (e && e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    }

    if (body.action === 'save_token') {
      return saveToken_(body.provider, body.tokens);
    }

    if (body.action === 'load_token') {
      return loadToken_(body.provider);
    }

    return saveCandidate_(body);
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) });
  }
}

function saveToken_(provider, tokens) {
  if (!provider || !tokens) {
    return jsonResponse({ ok: false, error: 'provider and tokens are required' });
  }
  var key = 'oauth_tokens_' + provider;
  PropertiesService.getScriptProperties().setProperty(key, JSON.stringify(tokens));
  return jsonResponse({ ok: true, saved: true, provider: provider });
}

function loadToken_(provider) {
  if (!provider) {
    return jsonResponse({ ok: false, error: 'provider is required' });
  }
  var key = 'oauth_tokens_' + provider;
  var raw = PropertiesService.getScriptProperties().getProperty(key);
  if (!raw) {
    return jsonResponse({ ok: false, tokens: null, error: 'token not found' });
  }
  return jsonResponse({ ok: true, provider: provider, tokens: JSON.parse(raw) });
}

function saveCandidate_(row) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('Candidates') || ss.insertSheet('Candidates');

  var headers = [
    'Date Added',
    'Source',
    'Vacancy',
    'Candidate Name',
    'Location',
    'Experience',
    'Skills',
    'GPT Score',
    'Status',
    'Recruiter Comment',
    'Resume Link',
    'Suggested Reply',
    'GPT Summary'
  ];

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(headers);
  }

  sheet.appendRow([
    row.date_added || new Date().toISOString(),
    row.source || '',
    row.vacancy || '',
    row.candidate_name || '',
    row.location || '',
    row.experience || '',
    row.skills || '',
    row.gpt_score || '',
    row.status || '',
    row.recruiter_comment || '',
    row.resume_link || '',
    row.suggested_reply || '',
    row.gpt_summary || ''
  ]);

  return jsonResponse({ ok: true, saved: true });
}
