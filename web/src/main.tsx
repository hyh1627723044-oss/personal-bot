import ReactDOM from 'react-dom/client';
import { useState } from 'react';
import { PipecatClient } from '@pipecat-ai/client-js';
import { PipecatClientAudio, PipecatClientProvider } from '@pipecat-ai/client-react';
import { createClient } from './client';
import App from './App';
import './style.css';

function Root() {
  const [client, setClient] = useState<PipecatClient>(createClient);
  return <PipecatClientProvider client={client}>
    <App onClientCreated={setClient} />
    <PipecatClientAudio />
  </PipecatClientProvider>;
}

ReactDOM.createRoot(document.getElementById('root')!).render(<Root />);
