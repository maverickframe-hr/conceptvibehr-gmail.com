/**
 * Maverickframe HR Bridge Google Apps Script
 * - Stores OAuth tokens persistently in Script Properties
 * - Saves selected candidates to the Candidates sheet
 * - Reads HH/Rabota notification emails from Gmail without modifying them
 */
var TOKEN_STORE_VERSION = '0.5.0';

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
    if (params.action === 'read_hh_emails') {
      return readHHEmails_(params);
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

    if (body.action === 'read_hh_emails') {
      return readHHEmails_(body);
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

function parseBool_(value) {
  if (value === true) {
    return true;
  }
  if (typeof value === 'string') {
    return /^(true|1|yes)$/i.test(value);
  }
  return false;
}

function boundedInt_(value, defaultValue, minValue, maxValue) {
  var number = parseInt(value, 10);
  if (isNaN(number)) {
    number = defaultValue;
  }
  return Math.max(minValue, Math.min(maxValue, number));
}

function cleanText_(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function truncate_(text, maxLength) {
  text = String(text || '');
  if (text.length <= maxLength) {
    return text;
  }
  return text.substring(0, maxLength - 3) + '...';
}

function extractUrls_(text) {
  var urls = [];
  var seen = {};
  var match;
  var regex = /https?:\/\/[^\s<>"')]+/g;
  while ((match = regex.exec(String(text || ''))) !== null && urls.length < 10) {
    var url = match[0].replace(/[.,;:!?]+$/, '');
    if (!seen[url]) {
      seen[url] = true;
      urls.push(url);
    }
  }
  return urls;
}

function extractVacancy_(text) {
  var match = String(text || '').match(/(?:на\s+)?ваканси[яю]\s+([^:\n\r]+)/i);
  if (!match) {
    return null;
  }
  return cleanText_(match[1]);
}

function buildHHEmailQuery_(options) {
  if (options.query) {
    return String(options.query);
  }

  var query = '{from:hh.ru from:hh.uz from:rabota.by subject:hh subject:HeadHunter subject:rabota} -in:spam -in:trash';
  var newerThanDays = boundedInt_(options.newer_than_days || options.newerThanDays, 30, 1, 365);
  query += ' newer_than:' + newerThanDays + 'd';
  if (parseBool_(options.unread_only || options.unreadOnly)) {
    query += ' is:unread';
  }
  return query;
}

function latestThreadMessage_(thread) {
  var messages = thread.getMessages();
  return messages[messages.length - 1];
}

function summarizeHHMessage_(thread, message, includeBody) {
  var plainBody = message.getPlainBody() || '';
  var htmlBody = message.getBody() || '';
  var bodyForLinks = plainBody + '\n' + htmlBody;
  var body = truncate_(plainBody, 4000);
  var snippet = truncate_(cleanText_(plainBody), 500);

  var item = {
    id: message.getId(),
    thread_id: thread.getId(),
    date: message.getDate().toISOString(),
    from: message.getFrom(),
    to: message.getTo(),
    subject: message.getSubject(),
    snippet: snippet,
    vacancy: extractVacancy_(plainBody),
    urls: extractUrls_(bodyForLinks),
    unread: message.isUnread()
  };

  if (includeBody) {
    item.body = body;
  }

  return item;
}

function readHHEmails_(options) {
  options = options || {};
  var maxResults = boundedInt_(options.max_results || options.maxResults, 10, 1, 50);
  var includeBody = parseBool_(options.include_body || options.includeBody);
  var query = buildHHEmailQuery_(options);
  var threads = GmailApp.search(query, 0, maxResults);
  var emails = [];

  for (var i = 0; i < threads.length; i++) {
    emails.push(summarizeHHMessage_(threads[i], latestThreadMessage_(threads[i]), includeBody));
  }

  console.log('readHHEmails query=%s returned=%s includeBody=%s', query, emails.length, includeBody);
  return jsonResponse({
    ok: true,
    query: query,
    max_results: maxResults,
    returned: emails.length,
    emails: emails
  });
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
