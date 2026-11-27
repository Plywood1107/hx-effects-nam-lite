/* beats.js - the groove editor's library: starting points written for this project (not transcriptions, no MIDI or
 * audio from anyone), each after the feel of a well-known drum part, at about its tempo. Edit them freely.
 * One string a sound, one character a sixteenth ("x" a hit), bars one after another; num/den the time signature.
 * Sounds: K kick, S snare, H hat, O open hat / cymbal, T1..T4 toms (high .. floor). */
(function (root) {
  "use strict";
  var B = [
    { name: "Back in Black feel", by: "AC/DC", bpm: 94, num: 4, den: 4, bars: 1,
      K: "x.......x.x.....", S: "....x.......x...", H: "x.x.x.x.x.x.x.x." },
    { name: "Highway to Hell feel", by: "AC/DC", bpm: 116, num: 4, den: 4, bars: 1,
      K: "x.......x.......", S: "....x.......x...", H: "x.x.x.x.x.x.x.x." },
    { name: "No One Knows feel", by: "Queens of the Stone Age", bpm: 85, num: 4, den: 4, bars: 1,
      K: "x..x..x...x..x..", S: "....x.......x...", H: "x.x.x.x.x.x.x.x." },
    { name: "Smells Like Teen Spirit feel", by: "Nirvana", bpm: 117, num: 4, den: 4, bars: 2,
      K: "x.x.....x.x.....x.x.....x.x.....", S: "....x.......x.......x.......x...",
      H: "x.x.x.x.x.x.x.x.................", O: "................x.x.x.x.x.x.x.x." },
    { name: "Scentless Apprentice feel", by: "Nirvana", bpm: 98, num: 4, den: 4, bars: 2,
      K: "x.......x...x...x.......x...x...", S: "....x.......x.......x.......x...",
      T4: "x.x.x.x.x.x.x.x.x...x...x...x...", T3: "..................x...x...x...x." },
    { name: "Enter Sandman feel", by: "Metallica", bpm: 123, num: 4, den: 4, bars: 1,
      K: "x.....x.x.......", S: "....x.......x...", H: "x.x.x.x.x.x.x.x." },
    { name: "Firestarter feel", by: "The Prodigy", bpm: 141, num: 4, den: 4, bars: 2,
      K: "x.........x.....x.x.......x..x..", S: "....x..x.x..x.......x..x.x..x..x",
      H: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx..", O: "..............................x." },
    { name: "New Noise feel", by: "Refused", bpm: 190, num: 4, den: 4, bars: 2,
      K: "x...x...x...x...x.x.x.x.x.x.x.x.", S: "..x...x...x...x...x...x...x...x.", O: "x...x...x...x...x...x...x...x..." },
    { name: "Seven Nation Army feel", by: "The White Stripes", bpm: 124, num: 4, den: 4, bars: 1,
      K: "x...x...x...x...", S: "....x.......x...", O: "x..............." },
    { name: "Song 2 feel", by: "Blur", bpm: 130, num: 4, den: 4, bars: 1,
      K: "x..x..x.x..x..x.", S: "....x.......x...", O: "x.x.x.x.x.x.x.x." },
    { name: "We Will Rock You feel", by: "Queen", bpm: 81, num: 4, den: 4, bars: 1,
      K: "x.x.....x.x.....", S: "....x.......x..." },
    { name: "Killing in the Name feel", by: "Rage Against the Machine", bpm: 88, num: 4, den: 4, bars: 1,
      K: "x.....x...x.....", S: "....x.......x...", H: "x.x.x.x.x.x.x.x." },
    { name: "Everlong feel", by: "Foo Fighters", bpm: 158, num: 4, den: 4, bars: 1,
      K: "x.....x.x.....x.", S: "....x.......x...", H: "xxxxxxxxxxxxxxxx" },
    { name: "When the Levee Breaks feel", by: "Led Zeppelin", bpm: 71, num: 4, den: 4, bars: 1,
      K: "xx.....x..x.....", S: "....x.......x...", H: "x.x.x.x.x.x.x.x." },
    { name: "Fill: toms down", by: "", bpm: 120, num: 4, den: 4, bars: 1,
      K: "x...............", S: "x.x.............", T1: "....xx..........", T2: "......xx........", T3: "........xx.x....",
      T4: "..........x.xxxx" },
    { name: "Odd 7/8 rock", by: "", bpm: 140, num: 7, den: 8, bars: 2,
      K: "x.......x....." + "x.......x.x...", S: "....x......x.." + "....x......x.x", H: "x.x.x.x.x.x.x." + "x.x.x.x.x.x.x." },
    { name: "12/8 shuffle", by: "", bpm: 72, num: 12, den: 8, bars: 1,
      K: "x...........x...........", S: "......x...........x.....", H: "x.x.x.x.x.x.x.x.x.x.x.x." },
    { name: "6/8 ballad", by: "", bpm: 60, num: 6, den: 8, bars: 1,
      K: "x...........", S: "......x.....", H: "x.x.x.x.x.x." },
    { name: "Half-time sludge", by: "", bpm: 70, num: 4, den: 4, bars: 1,
      K: "x.....x...x.....", S: "........x.......", O: "x...x...x...x..." },
    { name: "Motorik", by: "", bpm: 128, num: 4, den: 4, bars: 1,
      K: "x...x...x.x.x...", S: "....x.......x...", H: "xxxxxxxxxxxxxxxx" },
  ];
  if (typeof module !== "undefined" && module.exports) module.exports = B; else root.GROOVE_BEATS = B;
})(this);
