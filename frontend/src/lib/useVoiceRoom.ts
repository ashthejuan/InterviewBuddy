"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ConnectionState,
  Room,
  RoomEvent,
  Track,
  createLocalAudioTrack,
  type LocalAudioTrack,
  type Participant,
  type RemoteTrack,
} from "livekit-client";
import { getVoiceToken } from "@/lib/api";
import {
  AGENT_DROPPED_MESSAGE,
  AGENT_JOIN_TIMEOUT_MS,
  ATTR_AGENT_STATE,
  ATTR_SEGMENT_ID,
  ATTR_TRANSCRIPTION_FINAL,
  NOTHING_HEARD_MESSAGE,
  RPC_CLEAR_ANSWER,
  RPC_SUBMIT_ANSWER,
  SUBMIT_RPC_TIMEOUT_MS,
  TRANSCRIPTION_TOPIC,
  describeVoiceError,
  phaseFromConnectionState,
  upsertHeardSegment,
  type HeardSegment,
  type VoicePhase,
} from "@/lib/voice";

// Never leave Submit locked if the agent fails to speak a reply.
const REPLY_FALLBACK_MS = 90_000;

export function useVoiceRoom(sessionId: string) {
  const roomRef = useRef<Room | null>(null);
  const micRef = useRef<LocalAudioTrack | null>(null);
  const audioHostRef = useRef<HTMLDivElement | null>(null);
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [muted, setMuted] = useState(false);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentJoined, setAgentJoined] = useState(false);
  const [agentState, setAgentState] = useState<string | null>(null);
  const [agentLate, setAgentLate] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [heard, setHeard] = useState<HeardSegment[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [awaitingReply, setAwaitingReply] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const agentIdentityRef = useRef<string | null>(null);

  const teardown = useCallback(async () => {
    const room = roomRef.current;
    roomRef.current = null;
    micRef.current?.stop();
    micRef.current = null;
    if (room) await room.disconnect();
    audioHostRef.current?.replaceChildren();
    setAgentSpeaking(false);
    setUserSpeaking(false);
    setAgentJoined(false);
    setAgentState(null);
    setSubmitting(false);
    setAwaitingReply(false);
    agentIdentityRef.current = null;
  }, []);

  const join = useCallback(async () => {
    if (roomRef.current) return;
    setError(null);
    setNotice(null);
    setMuted(false);
    setHeard([]);
    setAgentLate(false);
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

      const trackAgent = (p: Participant) => {
        if (!p.isAgent) return;
        agentIdentityRef.current = p.identity;
        setAgentJoined(true);
        const state = p.attributes[ATTR_AGENT_STATE] ?? null;
        setAgentState(state);
        // A new question starts a fresh answer.
        if (state === "speaking") {
          setHeard([]);
          setAwaitingReply(false);
          setNotice(null);
        }
      };

      // The agent publishes the candidate's STT under the candidate's identity.
      room.registerTextStreamHandler(TRANSCRIPTION_TOPIC, async (reader, from) => {
        if (from.identity !== room.localParticipant.identity) return;
        const attrs = reader.info.attributes ?? {};
        const text = await reader.readAll();
        setHeard((prev) =>
          upsertHeardSegment(prev, {
            id: attrs[ATTR_SEGMENT_ID] ?? reader.info.id,
            text,
            final: attrs[ATTR_TRANSCRIPTION_FINAL] === "true",
          }),
        );
      });

      room
        .on(RoomEvent.ParticipantConnected, trackAgent)
        .on(RoomEvent.ParticipantAttributesChanged, (_changed, p) => trackAgent(p))
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
          setUserSpeaking(speakers.some((p) => p.identity === self));
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
          setUserSpeaking(false);
          setAgentJoined(false);
          setAgentState(null);
          setPhase("disconnected");
        });

      await room.connect(grant.server_url, grant.token);
      room.remoteParticipants.forEach(trackAgent);
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

  const callAgent = useCallback(async (method: string, responseTimeout?: number) => {
    const room = roomRef.current;
    const agent = agentIdentityRef.current;
    if (!room || !agent) throw new Error("The interviewer isn't in the call.");
    return room.localParticipant.performRpc({
      destinationIdentity: agent,
      method,
      payload: "",
      responseTimeout,
    });
  }, []);

  const submitAnswer = useCallback(async () => {
    setSubmitting(true);
    setNotice(null);
    try {
      const raw = await callAgent(RPC_SUBMIT_ANSWER, SUBMIT_RPC_TIMEOUT_MS);
      const transcript = String(JSON.parse(raw)?.transcript ?? "").trim();
      if (transcript) setAwaitingReply(true);
      else setNotice(NOTHING_HEARD_MESSAGE);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Submitting the answer failed.");
    } finally {
      setSubmitting(false);
    }
  }, [callAgent]);

  const clearAnswer = useCallback(async () => {
    setNotice(null);
    try {
      await callAgent(RPC_CLEAR_ANSWER);
      setHeard([]);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Clearing the answer failed.");
    }
  }, [callAgent]);

  const unlockAudio = useCallback(async () => {
    await roomRef.current?.startAudio();
    setAudioBlocked(false);
  }, []);

  useEffect(() => {
    if (phase !== "connected" || agentJoined) return;
    const id = window.setTimeout(() => setAgentLate(true), AGENT_JOIN_TIMEOUT_MS);
    return () => window.clearTimeout(id);
  }, [phase, agentJoined]);

  useEffect(() => {
    if (!awaitingReply) return;
    const id = window.setTimeout(() => setAwaitingReply(false), REPLY_FALLBACK_MS);
    return () => window.clearTimeout(id);
  }, [awaitingReply]);

  useEffect(() => {
    return () => {
      void teardown();
    };
  }, [teardown]);

  return {
    phase,
    muted,
    agentSpeaking,
    agentJoined,
    agentState,
    agentLate: agentLate && !agentJoined,
    userSpeaking,
    heard,
    submitting,
    awaitingReply,
    notice,
    submitAnswer,
    clearAnswer,
    audioBlocked,
    error,
    audioHostRef,
    join,
    leave: teardown,
    toggleMute,
    unlockAudio,
  };
}
