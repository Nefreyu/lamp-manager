<?php

declare(strict_types=1);

function e(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

$host = (string) ($_SERVER['HTTP_HOST'] ?? 'localhost');
$domain = preg_replace('/:\d+$/', '', $host);
$project = preg_replace('/\.test$/', '', $domain);
$software = (string) ($_SERVER['SERVER_SOFTWARE'] ?? '');
$server = match (true) {
    stripos($software, 'nginx') !== false => 'Nginx',
    stripos($software, 'apache') !== false => 'Apache',
    $software !== '' => strtok($software, ' '),
    default => 'servidor desconocido',
};

$environment = [
    'Servidor' => $software !== '' ? $software : $server,
    'Docroot' => (string) ($_SERVER['DOCUMENT_ROOT'] ?? __DIR__),
    'Hora' => date('d/m/Y H:i:s'),
    'Zona horaria' => date_default_timezone_get(),
];

$config = [
    'memory_limit' => (string) ini_get('memory_limit'),
    'upload_max_filesize' => (string) ini_get('upload_max_filesize'),
    'max_execution_time' => ini_get('max_execution_time') . ' s',
    'display_errors' => filter_var(ini_get('display_errors'), FILTER_VALIDATE_BOOLEAN) ? 'On' : 'Off',
];

$extensions = [];
foreach (['pdo_mysql', 'mbstring', 'intl', 'gd', 'curl', 'zip', 'opcache' => 'Zend OPcache', 'xdebug'] as $key => $ext) {
    $label = is_string($key) ? $key : $ext;
    $extensions[$label] = extension_loaded($ext);
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= e($domain) ?></title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #f5f7fb;
      --surface: #ffffff;
      --border: #e2e8f0;
      --text: #0f172a;
      --text-muted: #64748b;
      --accent: #4f5b93;
      --accent-soft: rgba(79, 91, 147, 0.10);
      --ok: #16a34a;
      --ok-soft: rgba(22, 163, 74, 0.12);
      --off: #94a3b8;
      --code-bg: #f1f5f9;
      --glow: rgba(119, 123, 180, 0.18);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #0f172a;
        --surface: #1e293b;
        --border: #334155;
        --text: #f1f5f9;
        --text-muted: #94a3b8;
        --accent: #8892bf;
        --accent-soft: rgba(136, 146, 191, 0.14);
        --ok: #4ade80;
        --ok-soft: rgba(74, 222, 128, 0.12);
        --off: #64748b;
        --code-bg: #0f172a;
        --glow: rgba(119, 123, 180, 0.22);
      }
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Cantarell, sans-serif;
      background: radial-gradient(1000px 480px at 50% -10%, var(--glow) 0%, transparent 60%), var(--bg);
      background-attachment: fixed;
      color: var(--text);
      min-height: 100vh;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }
    .wrap { max-width: 980px; margin: 0 auto; padding: 48px 24px 64px; }
    .hero {
      display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
      padding: 28px; margin-bottom: 24px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
      position: relative; overflow: hidden;
    }
    .hero::after {
      content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 3px;
      background: linear-gradient(90deg, #777bb4, #4f5b93 40%, transparent 85%);
    }
    .php-logo {
      width: 64px; height: 64px; border-radius: 16px; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      background: linear-gradient(135deg, #8892bf, #4f5b93);
      box-shadow: 0 8px 20px -6px rgba(79, 91, 147, 0.6);
      color: #fff; font: 800 1.35rem/1 'Segoe UI', Cantarell, sans-serif; font-style: italic;
      letter-spacing: -0.02em;
    }
    .hero-text { flex: 1; min-width: 220px; }
    .hero h1 { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; word-break: break-all; }
    .hero p { color: var(--text-muted); font-size: 0.95rem; }
    .badges { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge {
      font-size: 0.8rem; font-weight: 600; padding: 5px 12px; border-radius: 999px;
      background: var(--accent-soft); color: var(--accent); white-space: nowrap;
    }
    .badge.live { background: var(--ok-soft); color: var(--ok); display: inline-flex; align-items: center; gap: 6px; }
    .badge.live::before {
      content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--ok);
      animation: pulse 2s ease-in-out infinite;
    }
    @keyframes pulse { 50% { opacity: 0.35; } }
    @media (prefers-reduced-motion: reduce) { .badge.live::before { animation: none; } }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
    @media (max-width: 720px) {
      .grid { grid-template-columns: minmax(0, 1fr); }
      .wrap { padding: 24px 16px 48px; }
    }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 22px 24px; }
    .card h2 {
      font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--text-muted); margin-bottom: 14px;
    }
    dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 10px 16px; font-size: 0.9rem; }
    dt { color: var(--text-muted); }
    dd { text-align: right; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
    code { font-family: ui-monospace, 'Cascadia Code', 'DejaVu Sans Mono', monospace; font-size: 0.85em; }
    .exts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .ext {
      display: flex; align-items: center; gap: 8px; font-size: 0.88rem;
      padding: 8px 10px; border-radius: 10px; border: 1px solid var(--border);
    }
    .ext .mark { font-weight: 700; width: 1em; text-align: center; }
    .ext.on .mark { color: var(--ok); }
    .ext.off { color: var(--off); }
    ol { list-style: none; counter-reset: step; display: grid; gap: 14px; font-size: 0.9rem; }
    ol li { counter-increment: step; display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 10px; }
    ol li::before {
      content: counter(step); width: 28px; height: 28px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      background: var(--accent-soft); color: var(--accent); font-weight: 700; font-size: 0.85rem;
    }
    .path {
      display: block; margin-top: 4px; padding: 6px 10px; border-radius: 8px;
      background: var(--code-bg); border: 1px solid var(--border); overflow-wrap: anywhere;
    }
    a { color: var(--accent); font-weight: 600; }
    footer { margin-top: 32px; text-align: center; font-size: 0.8rem; color: var(--text-muted); }
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div class="php-logo" aria-hidden="true">php</div>
      <div class="hero-text">
        <h1><?= e($domain) ?></h1>
        <p>Proyecto PHP listo · servido por <?= e($server) ?></p>
      </div>
      <div class="badges">
        <span class="badge">PHP <?= e(PHP_VERSION) ?></span>
        <span class="badge"><?= e(PHP_SAPI) ?></span>
        <span class="badge live">En línea</span>
      </div>
    </header>

    <div class="grid">
      <section class="card">
        <h2>Entorno</h2>
        <dl>
          <?php foreach ($environment as $label => $value): ?>
            <dt><?= e($label) ?></dt>
            <dd><?= e($value) ?></dd>
          <?php endforeach; ?>
        </dl>
      </section>

      <section class="card">
        <h2>Configuración PHP</h2>
        <dl>
          <?php foreach ($config as $label => $value): ?>
            <dt><code><?= e($label) ?></code></dt>
            <dd><?= e($value) ?></dd>
          <?php endforeach; ?>
        </dl>
      </section>

      <section class="card">
        <h2>Extensiones</h2>
        <div class="exts">
          <?php foreach ($extensions as $name => $loaded): ?>
            <div class="ext <?= $loaded ? 'on' : 'off' ?>">
              <span class="mark"><?= $loaded ? '✓' : '✗' ?></span>
              <code><?= e($name) ?></code>
            </div>
          <?php endforeach; ?>
        </div>
      </section>

      <section class="card">
        <h2>Primeros pasos</h2>
        <ol>
          <li><div>Edita este fichero para empezar:<code class="path"><?= e(__FILE__) ?></code></div></li>
          <li><div>Base de datos MySQL creada: <code><?= e($project) ?></code></div></li>
          <li><div>Vuelve al panel con todos tus proyectos: <a href="http://localhost">localhost</a></div></li>
        </ol>
      </section>
    </div>

    <footer>Generado por LAMP Manager</footer>
  </div>
</body>
</html>
