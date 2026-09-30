"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ConnectionState,
  Room,
  RoomEvent,
  Track,
  createLocalAudioTrack,
  type LocalAudioTrack,
  type RemoteTrack,
} from "livekit-client";
import { getVoiceToken } from "@/lib/api";
import {
  AGENT_DROPPED_MESSAGE,
  describeVoiceError,
  phaseFromConnectionState,
  type VoicePhase,
} from "@/lib/voice";

export function useVoiceRoom(sessionId: string) {
  const roomRef = useRef<Room | null>(null);
  const micRef = useRef<LocalAudioTrack | null>(null);
  const audioHostRef = useRef<HTMLDivElement | null>(null);
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [muted, setMuted] = useState(false);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const teardown = useCallback(async () => {
    const room = roomRef.current;
    roomRef.current = null;
    micRef.current?.stop();
    micRef.current = null;
    if (room) await room.disconnect();
    audioHostRef.current?.replaceChildren();
    setAgentSpeaking(false);
  }, []);

  const join = useCallback(async () => {
    if (roomRef.current) return;
    setError(null);
    setMuted(false);
    try {
      // Mic first: failing after connect would drop the candidate and wrap the interview.
      setPhase("requesting_mic");
      const mic = await createLocalAudioTrack({
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
      micRef.current = mic;

      setPhase("connecting");
      const grant = await getVoiceToken(sessionId);
      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room
        .on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
          setPhase(phaseFromConnectionState(state));
        })
        .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
          if (track.kind !== Track.Kind.Audio) return;
          audioHostRef.current?.appendChild(track.attach());
        })
        .on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
          track.detach().forEach((el) => el.remove());
        })
        .on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
          const self = room.localParticipant.identity;
          setAgentSpeaking(speakers.some((p) => p.identity !== self));
        })
        .on(RoomEvent.AudioPlaybackStatusChanged, () => {
          setAudioBlocked(!room.canPlaybackAudio);
        })
        .on(RoomEvent.ParticipantDisconnected, (participant) => {
          if (!participant.isAgent) return;
          void teardown().then(() => {
            setError(AGENT_DROPPED_MESSAGE);
            setPhase("error");
          });
        })
        .on(RoomEvent.Disconnected, () => {
          micRef.current?.stop();
          micRef.current = null;
          roomRef.current = null;
          setAgentSpeaking(false);
          setPhase("disconnected");
        });

      await room.connect(grant.server_url, grant.token);
      await room.localParticipant.publishTrack(mic, {
        source: Track.Source.Microphone,
      });
      setAudioBlocked(!room.canPlaybackAudio);
      setPhase("connected");
    } catch (err) {
      await teardown();
      setError(describeVoiceError(err));
      setPhase("error");
    }
  }, [sessionId, teardown]);

  const toggleMute = useCallback(async () => {
    const mic = micRef.current;
    if (!mic) return;
    if (mic.isMuted) {
      await mic.unmute();
      setMuted(false);
    } else {
      await mic.mute();
      setMuted(true);
    }
  }, []);

  const unlockAudio = useCallback(async () => {
    await roomRef.current?.startAudio();
    setAudioBlocked(false);
  }, []);

  useEffect(() => {
    return () => {
      void teardown();
    };
  }, [teardown]);

  return {
    phase,
    muted,
    agentSpeaking,
    audioBlocked,
    error,
    audioHostRef,
    join,
    leave: teardown,
    toggleMute,
    unlockAudio,
  };
}
