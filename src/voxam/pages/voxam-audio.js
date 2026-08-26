/* VΘXΔM's sound dialect: the vocabulary GlkOte never grew.

   Updates may carry a "sounds" array of channel operations --
   play, stop, volume -- each play with its sound inlined whole as
   a data: url in a container the browser decodes (WAVE or Ogg).
   This module drives them through Web Audio: one gain node per
   channel, counted repeats by re-triggering, forever as a native
   loop, and volume fades as gain ramps. A play that finishes
   naturally reports back as a {type: "sound"} event through the
   sender given to start(), stamped with the latest generation
   seen, so the interpreter's model can fall silent with it.

   Browsers gate audio behind a user gesture: the context resumes
   on the first key or pointer press, so a sound started before
   any interaction begins as soon as one arrives. */

var VoxamAudio = (function() {
    var context = null;
    var send = null;
    var gen = 0;
    var channels = {};

    function ensure() {
        if (!context) {
            var AC = window.AudioContext || window.webkitAudioContext;
            if (!AC)
                return null;
            context = new AC();
            var unlock = function() {
                if (context && context.state === 'suspended')
                    context.resume();
            };
            document.addEventListener('keydown', unlock, true);
            document.addEventListener('pointerdown', unlock, true);
        }
        return context;
    }

    function channel(id) {
        if (!channels[id]) {
            var ctx = ensure();
            if (!ctx)
                return null;
            var gain = ctx.createGain();
            gain.connect(ctx.destination);
            channels[id] = { gain: gain, source: null, token: 0 };
        }
        return channels[id];
    }

    function bytes(url) {
        var raw = atob(url.slice(url.indexOf(',') + 1));
        var held = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++)
            held[i] = raw.charCodeAt(i);
        return held.buffer;
    }

    /* Silence a channel's current source without an end report:
       a stopped or replaced sound is not a natural ending. The
       token tears any in-flight decode or repeat chain off the
       channel. */
    function hush(ch) {
        ch.token += 1;
        if (ch.source) {
            ch.source.onended = null;
            try { ch.source.stop(); } catch (err) { }
            ch.source = null;
        }
    }

    function play(id, op) {
        var ch = channel(id);
        if (!ch)
            return;
        hush(ch);
        ch.gain.gain.value = op.volume;
        var mine = ch.token;
        var remaining = op.repeats;
        context.decodeAudioData(bytes(op.url)).then(function(buffer) {
            var start = function() {
                if (ch.token !== mine)
                    return;
                var source = context.createBufferSource();
                source.buffer = buffer;
                source.connect(ch.gain);
                if (remaining < 0) {
                    source.loop = true;
                } else {
                    source.onended = function() {
                        if (ch.token !== mine)
                            return;
                        remaining -= 1;
                        if (remaining > 0) {
                            start();
                            return;
                        }
                        ch.source = null;
                        if (send)
                            send({ type: 'sound', gen: gen, channel: id,
                                   sound: op.sound, notify: op.notify });
                    };
                }
                ch.source = source;
                source.start();
            };
            start();
        }).catch(function() { });
    }

    function volume(id, op) {
        var ch = channel(id);
        if (!ch)
            return;
        var gain = ch.gain.gain;
        if (op.duration > 0) {
            gain.cancelScheduledValues(context.currentTime);
            gain.setValueAtTime(gain.value, context.currentTime);
            gain.linearRampToValueAtTime(
                op.volume, context.currentTime + op.duration / 1000);
        } else {
            gain.value = op.volume;
        }
    }

    return {
        start: function(sender) {
            send = sender;
        },
        update: function(stanza) {
            if (!stanza)
                return;
            if (typeof stanza.gen === 'number')
                gen = stanza.gen;
            var ops = stanza.sounds || [];
            for (var i = 0; i < ops.length; i++) {
                var op = ops[i];
                if (op.op === 'play') {
                    play(op.channel, op);
                } else if (op.op === 'stop') {
                    if (channels[op.channel])
                        hush(channels[op.channel]);
                } else if (op.op === 'volume') {
                    volume(op.channel, op);
                }
            }
        }
    };
})();
