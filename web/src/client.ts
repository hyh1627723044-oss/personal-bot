import { PipecatClient } from '@pipecat-ai/client-js';
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport';

export function createClient() {
  return new PipecatClient({
    transport: new SmallWebRTCTransport(),
    enableMic: true,
    enableCam: false,
    disconnectOnBotDisconnect: true,
  });
}

export function stopLocalTracks(client: PipecatClient) {
  for (const track of Object.values(client.tracks().local)) track?.stop();
}

export async function releaseClient(client: PipecatClient) {
  // SmallWebRTC can return early when disconnected before creating a peer.
  stopLocalTracks(client);
  try { await client.disconnect(); }
  finally { stopLocalTracks(client); }
}
