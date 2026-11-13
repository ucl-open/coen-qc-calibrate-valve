using Bonsai;
using OpenRigs.Core.Calibration;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.Linq;
using System.Reactive.Linq;

// Calibrating every valve in one run, interleaved (Pip, 7 Nov 2026: "an option to calibrate all
// valves (interleave left and right for each burst, obviously double number of calibrations) or each
// individual valve"). One container on one balance under every spout: each burst is weighed by
// difference before the next valve fires, so each valve's gain is its own.
//
// The procedure is expanded once, at load, so everything that follows the bursts (OpenRigs.Devices
// ManualBalance, which counts the pulses fired; RunCalibration; the weights file) sees one sample per
// valve per burst, in the order they fire. Every burst is a PulseTrain for OpenRigs.Core FirePulses,
// which fires it on the Harp clock at the procedure's one pulseGapMs, the gap a rig then fires its
// rewards at (plan v11). Compiled by Bonsai under C# 5.
namespace CoenQcCalibrateValve
{
    /// <summary>A sample of the expanded procedure: the procedure's own, on one valve.</summary>
    public class ValveSample : DispenseSample
    {
        int channel;

        /// <summary>The behavior board line this burst fires on, 1 to 3 (DO1 to DO3).</summary>
        public int Channel
        {
            get { return channel; }
            set { channel = value; }
        }
    }

    /// <summary>One train of pulses, mapped onto OpenRigs.Core FirePulses' properties (InputMapping).</summary>
    public class PulseTrain
    {
        public int Line { get; set; }
        public int WidthMs { get; set; }
        public int Count { get; set; }
        public int PulseGapMs { get; set; }

        public static PulseTrain Of(DispenseSample sample, int line, int count)
        {
            var valve = sample as ValveSample;
            return new PulseTrain { Line = valve != null ? valve.Channel : line, WidthMs = sample.Size, Count = count, PulseGapMs = sample.PulseGapMs };
        }
    }

    /// <summary>The valves of a run, from the Channels launch property or, when that is empty, Channel.</summary>
    public static class Valves
    {
        public static int[] Parse(string channels, int channel)
        {
            var text = (channels ?? "").Trim();
            if (text.Length == 0) return new[] { channel };
            var parsed = new List<int>();
            foreach (var part in text.Split(new[] { ',', ' ', ';' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var name = part.Trim();
                if (name.StartsWith("DO", StringComparison.OrdinalIgnoreCase)) name = name.Substring(2);
                int value;
                if (!int.TryParse(name, NumberStyles.Integer, CultureInfo.InvariantCulture, out value) || value < 1 || value > 3)
                {
                    throw new InvalidOperationException(string.Format(
                        "Channels '{0}' names '{1}', which is not a behavior board line (1 to 3, or DO1 to DO3).", channels, part));
                }
                if (parsed.Contains(value))
                {
                    throw new InvalidOperationException(string.Format("Channels '{0}' names line {1} twice.", channels, value));
                }
                parsed.Add(value);
            }
            if (parsed.Count == 0) return new[] { channel };
            return parsed.ToArray();
        }

        /// <summary>The valves of an expanded procedure, in the order they fire.</summary>
        public static int[] Of(DispenseProcedure procedure)
        {
            var found = new List<int>();
            foreach (var sample in procedure.Samples)
            {
                var valve = sample as ValveSample;
                if (valve != null && !found.Contains(valve.Channel)) found.Add(valve.Channel);
            }
            return found.ToArray();
        }

        /// <summary>The procedure's one pulseGapMs; refuses samples at different gaps, since the
        /// calibration file records one and a rig fires every reward at it.</summary>
        public static int Gap(DispenseProcedure procedure)
        {
            var gaps = procedure.Samples.Select(sample => sample.PulseGapMs).Distinct().OrderBy(gap => gap).ToArray();
            if (gaps.Length != 1)
            {
                throw new InvalidOperationException(string.Format(
                    "config\\valve-calibration.yml's samples are fired at {0} gaps ({1} ms); give every sample one pulseGapMs, the gap a rig fires its rewards at.",
                    gaps.Length, string.Join(", ", gaps.Select(gap => gap.ToString(CultureInfo.InvariantCulture)).ToArray())));
            }
            return gaps[0];
        }
    }

    [Combinator]
    [Description("Expands the valve calibration's procedure over the valves to calibrate: each round (each width's first sample, then each width's second, ...) in a new random order every run, each sample once per valve, in turn (DO1's burst, weighed, then DO2's, weighed, and so on), and the priming pulses once per valve. Channels lists the valves (such as 1, 2, or DO1, DO2); empty, the one Channel. Input: (the settings, rig.yml's valves); stops the workflow if a valve is not a RewardValve in rig.yml's wiring or the samples are at different pulseGapMs.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class InterleaveValves
    {
        int channel = 1;
        string channels = "";

        [Description("The one valve to calibrate, 1 to 3, when Channels is empty.")]
        public int Channel
        {
            get { return channel; }
            set { channel = value; }
        }

        [Description("The valves to calibrate together, interleaved, such as 1, 2. Empty: only Channel.")]
        public string Channels
        {
            get { return channels; }
            set { channels = value; }
        }

        public IObservable<DispenseCalibration> Process(IObservable<Tuple<DispenseCalibration, ValveRig>> source)
        {
            return source.Select(input =>
            {
                var valves = Valves.Parse(Channels, Channel);
                input.Item2.Check(valves);
                return Expand(input.Item1, valves, new Random());
            });
        }

        /// <summary>The settings with each sample once per valve, in turn, and the priming pulses once per valve.
        /// With `random`, each round is shuffled first (Pip, 11 Nov 2026: "Shuffle every round"): round k holds
        /// each width's k-th sample, the rounds stay in turn, and a new order is drawn every run. Without it,
        /// the samples as written.</summary>
        public static DispenseCalibration Expand(DispenseCalibration settings, int[] valves, Random random)
        {
            var procedure = settings.Procedure;
            if (procedure == null || procedure.Samples == null || procedure.Samples.Count == 0)
            {
                throw new InvalidOperationException("The valve calibration's procedure has no samples.");
            }
            Valves.Gap(procedure);
            var expanded = new List<DispenseSample>();
            foreach (var sample in random == null ? procedure.Samples : Shuffled(procedure.Samples, random))
            {
                foreach (var valve in valves)
                {
                    expanded.Add(new ValveSample
                    {
                        Size = sample.Size,
                        Repeats = sample.Repeats,
                        PulseGapMs = sample.PulseGapMs,
                        Channel = valve
                    });
                }
            }
            procedure.Samples = expanded;
            // ManualBalance counts the priming pulses as one burst: every valve's.
            procedure.PrimingPulses = procedure.PrimingPulses * valves.Length;
            return settings;
        }

        /// <summary>The samples by round (each width's first, then each width's second, ...), each round shuffled.</summary>
        public static List<DispenseSample> Shuffled(IList<DispenseSample> samples, Random random)
        {
            var seen = new Dictionary<int, int>();
            var rounds = new List<List<DispenseSample>>();
            foreach (var sample in samples)
            {
                int round;
                seen.TryGetValue(sample.Size, out round);
                seen[sample.Size] = round + 1;
                while (rounds.Count <= round) rounds.Add(new List<DispenseSample>());
                rounds[round].Add(sample);
            }
            var order = new List<DispenseSample>();
            foreach (var round in rounds)
            {
                for (int i = round.Count - 1; i > 0; i--)
                {
                    int j = random.Next(i + 1);
                    var swap = round[i]; round[i] = round[j]; round[j] = swap;
                }
                order.AddRange(round);
            }
            return order;
        }
    }

    [Combinator]
    [Description("Each sample as its burst: its pulses at its width on its valve (an expanded procedure's sample; any other on Channel), at its pulseGapMs. Fed the procedure, the priming bursts: an equal share of the priming pulses on each valve in turn, at the priming size and the procedure's pulseGapMs.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ValveTrains
    {
        int channel = 1;

        [Description("The line a sample that names no valve fires on, 1 to 3.")]
        public int Channel
        {
            get { return channel; }
            set { channel = value; }
        }

        public IObservable<PulseTrain> Process(IObservable<DispenseSample> source)
        {
            return source.Select(sample => PulseTrain.Of(sample, Channel, sample.Repeats));
        }

        public IObservable<PulseTrain> Process(IObservable<DispenseProcedure> source)
        {
            return source.SelectMany(procedure => Priming(procedure, Channel));
        }

        public static PulseTrain[] Priming(DispenseProcedure procedure, int channel)
        {
            if (procedure.Samples == null || procedure.Samples.Count == 0)
            {
                throw new InvalidOperationException("The dispense procedure has no samples to take the priming size from.");
            }
            var valves = Valves.Of(procedure);
            if (valves.Length == 0) valves = new[] { channel };
            int size = procedure.PrimingSize ?? procedure.Samples.Max(sample => sample.Size);
            int gap = Valves.Gap(procedure);
            int each = procedure.PrimingPulses / valves.Length;
            return valves.Select(valve => new PulseTrain { Line = valve, WidthMs = size, Count = each, PulseGapMs = gap }).ToArray();
        }
    }

    // Drips (Pip, 8 Nov 2026): a drop can hang on the spout after a burst and fall into the next
    // weighing, so once a weight is due rig-control fires short bursts of the width tested, one Drip
    // command at a time, until the balance's display moves, and only then reads it. A sample's drip
    // pulses are its own: they are added to its row's repeats.
    [Combinator]
    [Description("Each Drip command as a burst: its text is the pulse count and, for the baseline, the line (such as '1 DO2'). With a sample (second input), at the sample's width on its valve; with the procedure, at its largest sample's width on the line named, else its first valve. At the procedure's pulseGapMs.")]
    [WorkflowElementCategory(ElementCategory.Combinator)]
    public class DripTrains
    {
        int channel = 1;

        [Description("The line a sample that names no valve drips on, 1 to 3.")]
        public int Channel
        {
            get { return channel; }
            set { channel = value; }
        }

        public IObservable<PulseTrain> Process(IObservable<string> commands, IObservable<DispenseSample> sample)
        {
            return sample.Take(1).SelectMany(s => commands.Select(text => PulseTrain.Of(s, Channel, Parse(text).Item1)));
        }

        public IObservable<PulseTrain> Process(IObservable<string> commands, IObservable<DispenseProcedure> procedure)
        {
            return procedure.Take(1).SelectMany(p => commands.Select(text =>
            {
                var drip = Parse(text);
                var valves = Valves.Of(p);
                int line = drip.Item2 > 0 ? drip.Item2 : valves.Length > 0 ? valves[0] : Channel;
                return new PulseTrain { Line = line, WidthMs = p.Samples.Max(x => x.Size), Count = drip.Item1, PulseGapMs = Valves.Gap(p) };
            }));
        }

        /// <summary>A Drip command's (pulses, line), the line 0 when not named.</summary>
        public static Tuple<int, int> Parse(string text)
        {
            var parts = (text ?? "").Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries);
            int pulses;
            if (parts.Length < 1 || parts.Length > 2 || !int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out pulses)
                || pulses < 1 || pulses > 100)
            {
                throw new InvalidOperationException(string.Format(
                    "Drip '{0}' is not a drip: give its pulses, 1 to 100, and for the baseline the line, such as 1 DO2.", text));
            }
            return Tuple.Create(pulses, parts.Length == 2 ? Valves.Parse(parts[1], 1)[0] : 0);
        }
    }

    // A minimum width per rig (Pip, 12 Nov 2026: "set different min/max of calibration on different
    // rigs"; "Max opening should be 5 x min, so all just scale"): the procedure's widths are written
    // for a 20 ms minimum and scaled at Go to rig-control's MinPulseMs; the pulses stay as written.
    [Combinator]
    [Description("The procedure's widths scaled at Go so the smallest is MinPulseMs, each times MinPulseMs over the smallest written, rounded half away from zero; pulses, gaps and priming as written. Input: (MinPulseMs as text, the settings). In place, and idempotent, so every subscriber of the settings scales them alike.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ScaleWidths
    {
        public const int Lowest = 5, Highest = 100;

        public IObservable<DispenseCalibration> Process(IObservable<Tuple<string, DispenseCalibration>> source)
        {
            return source.Select(input => Scale(input.Item2, ParseMin(input.Item1)));
        }

        public static int ParseMin(string text)
        {
            int min;
            if (!int.TryParse((text ?? "").Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out min) || min < Lowest || min > Highest)
            {
                throw new InvalidOperationException(string.Format(
                    "MinPulseMs '{0}' is not a minimum width: give whole ms, {1} to {2}.", text, Lowest, Highest));
            }
            return min;
        }

        public static DispenseCalibration Scale(DispenseCalibration settings, int min)
        {
            var samples = settings.Procedure.Samples;
            int smallest = samples.Min(sample => sample.Size);
            foreach (var sample in samples)
            {
                sample.Size = (int)Math.Round((double)(sample.Size * min) / smallest, MidpointRounding.AwayFromZero);
            }
            return settings;
        }
    }

    // Testing a width before Start (Pip, 12 Nov 2026: "test the min opening time in the calibration
    // window before starting (and then can edit)"): pulses on TriggerCalibratedPulse alone, never on
    // BurstPulses, so ManualBalance does not count them.
    [Combinator]
    [Description("Each Test command as a burst: its text is the width in ms, the pulses and the line, such as '20 10 DO1', at the procedure's pulseGapMs. Input: (the command's text, the settings).")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class TestTrain
    {
        public IObservable<PulseTrain> Process(IObservable<Tuple<string, DispenseCalibration>> source)
        {
            return source.Select(input =>
            {
                var test = Parse(input.Item1);
                return new PulseTrain { Line = test.Item3, WidthMs = test.Item1, Count = test.Item2, PulseGapMs = Valves.Gap(input.Item2.Procedure) };
            });
        }

        /// <summary>A Test command's (width ms, pulses, line).</summary>
        public static Tuple<int, int, int> Parse(string text)
        {
            var parts = (text ?? "").Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries);
            int width, pulses;
            if (parts.Length != 3
                || !int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out width) || width < 1 || width > 5 * ScaleWidths.Highest
                || !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out pulses) || pulses < 1 || pulses > 100)
            {
                throw new InvalidOperationException(string.Format(
                    "Test '{0}' is not a test: give the width in ms (1 to {1}), the pulses (1 to 100) and the line, such as 20 10 DO1.", text, 5 * ScaleWidths.Highest));
            }
            return Tuple.Create(width, pulses, Valves.Parse(parts[2], 1)[0]);
        }
    }

    [Combinator]
    [Description("The valves of the expanded procedure as the run's target says them, such as DO1, DO2.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class DescribeValves
    {
        public IObservable<string> Process(IObservable<DispenseCalibration> source)
        {
            return source.Select(settings => string.Join(", ", Valves.Of(settings.Procedure).Select(v => "DO" + v).ToArray()));
        }
    }

    /// <summary>One row of the weights file.</summary>
    public class ValveWeighing
    {
        public double size { get; set; }
        public int repeats { get; set; }
        public double before { get; set; }
        public double after { get; set; }
        public int channel { get; set; }
        public int pulseGapMs { get; set; }
    }

    [Combinator]
    [Description("Each weighed burst as a row of the weights file: its pulse width in ms, its pulses (its drips included), the grams before and after it, the valve it fired on (1 to 3) and its pulseGapMs. Input: (((grams after, grams before), its sample), its drip pulses), RunCalibration's output with SampleDrips.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ValveWeighingRow
    {
        int channel = 1;

        [Description("The valve of a sample that names none, 1 to 3.")]
        public int Channel
        {
            get { return channel; }
            set { channel = value; }
        }

        public IObservable<ValveWeighing> Process(IObservable<Tuple<Tuple<Tuple<double, double>, DispenseSample>, int>> source)
        {
            return source.Select(input =>
            {
                var weighed = input.Item1;
                var valve = weighed.Item2 as ValveSample;
                return new ValveWeighing
                {
                    size = weighed.Item2.Size,
                    repeats = weighed.Item2.Repeats + input.Item2,
                    before = weighed.Item1.Item2,
                    after = weighed.Item1.Item1,
                    channel = valve != null ? valve.Channel : Channel,
                    pulseGapMs = weighed.Item2.PulseGapMs
                };
            });
        }
    }
}
