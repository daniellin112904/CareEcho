/** Start uvicorn with backend/.venv on Windows or Unix. */
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const backend = path.join(__dirname, "..", "backend");
const venv = path.join(backend, ".venv");
const win = path.join(venv, "Scripts", "python.exe");
const unix = path.join(venv, "bin", "python");
const py = fs.existsSync(win) ? win : unix;

if (!fs.existsSync(py)) {
  console.error(`No venv Python at ${win} or ${unix}. Create backend/.venv first.`);
  process.exit(1);
}

const child = spawn(py, ["-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"], {
  cwd: backend,
  stdio: "inherit",
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
