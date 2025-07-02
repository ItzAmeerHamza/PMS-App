const net = require('net');
const { spawn } = require('child_process');

const port = process.env.PORT ? (process.env.PORT - 100) : 3000;

process.env.ELECTRON_START_URL = `http://localhost:${port}`;
process.env.NODE_ENV = 'development';

const client = new net.Socket();

let isElectronStarted = false;

const tryConnectionWithReact = () => client.connect({ port }, () => {
  client.end();
  if (!isElectronStarted) {
    console.log(`Electron is Running at ${process.env.ELECTRON_START_URL}!`);
    isElectronStarted = true;
    
    // Use spawn instead of exec to keep the process alive
    const electronProcess = spawn('npm', ['run', 'electron'], {
      stdio: 'inherit',
      shell: true
    });
    
    electronProcess.on('close', (code) => {
      console.log(`Electron process exited with code ${code}`);
    });
  }
});

tryConnectionWithReact();

client.on('error', (_error) => {
  setTimeout(tryConnectionWithReact, 1000);
});
