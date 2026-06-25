/**
 * Maverickframe HR Bridge Google Apps Script
 * - Stores OAuth tokens persistently in Script Properties
 * - Saves selected candidates to the Candidates sheet
 */
var TOKEN_STORE_VERSION = '0.4.1';

function tokenSummary_(tokens) {
  tokens = tokens || {};
  return {
    has_access_token: Boolean(tokens.access_token),
    has_refresh_token: Boolean(tokens.refresh_token),
    token_type: tokens.token_type || null,
    expires_in: tokens.expires_in || null,
    keys: Object.keys(tokens).sort()
  };
}

function jsonResponse(obj) {
  obj.version = obj.version || TOKEN_STORE_VERSION;
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function parseBody_(e) {
  var body = {};
  if (e && e.postData && e.postData.contents) {
    body = JSON.parse(e.postData.contents);
  }
  return body;
}

function doGet(e) {
  try {
    var params = (e && e.parameter) ? e.parameter : {};
    console.log('doGet action=%s provider=%s version=%s', params.action || '', params.provider || '', TOKEN_STORE_VERSION);
    if (params.action === 'load_token') {
      return loadToken_(params.provider);
    }
    if (params.action === 'ping') {
      return jsonResponse({ ok: true, service: 'Maverickframe HR token store and candidate database', ping: true });
    }
    return jsonResponse({ ok: true, service: 'Maverickframe HR token store and candidate database' });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) });
  }
}

function doPost(e) {
  try {
    var body = parseBody_(e);
    console.log('doPost action=%s provider=%s version=%s', body.action || 'save_candidate', body.provider || '', TOKEN_STORE_VERSION);

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
  console.log('saveToken provider=%s summary=%s', provider, JSON.stringify(tokenSummary_(tokens)));
  return jsonResponse({ ok: true, saved: true, provider: provider });
}

function loadToken_(provider) {
  if (!provider) {
    return jsonResponse({ ok: false, error: 'provider is required' });
  }
  var key = 'oauth_tokens_' + provider;
  var raw = PropertiesService.getScriptProperties().getProperty(key);
  if (!raw) {
    console.log('loadToken provider=%s found=false', provider);
    return jsonResponse({ ok: false, tokens: null, error: 'token not found' });
  }
  var tokens = JSON.parse(raw);
  console.log('loadToken provider=%s found=true summary=%s', provider, JSON.stringify(tokenSummary_(tokens)));
  return jsonResponse({ ok: true, provider: provider, tokens: tokens });
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

  console.log('saveCandidate saved=true source=%s', row.source || '');
  return jsonResponse({ ok: true, saved: true });
}
