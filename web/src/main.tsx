import ReactDOM from 'react-dom/client';
import { PipecatClient } from '@pipecat-ai/client-js';
import { PipecatClientAudio, PipecatClientProvider } from '@pipecat-ai/client-react';
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport';
import App from './App';
import './style.css';

const client = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableMic: true,
  enableCam: false,
});

window.addEventListener('pagehide', () => { void client.disconnect(); });

ReactDOM.createRoot(document.getElementById('root')!).render(
  <PipecatClientProvider client={client}>
    <App />
    <PipecatClientAudio />
  </PipecatClientProvider>,
);
