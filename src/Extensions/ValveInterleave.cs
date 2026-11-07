using Bonsai;
using OpenRigs.Core;
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
// valve per burst, in the order they fire. Compiled by Bonsai under C# 5.
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
    }

    [Combinator]
    [Description("Expands the valve calibration's procedure over the valves to calibrate: each sample once per valve, in turn (DO1's burst, weighed, then DO2's, weighed, and so on), and the priming pulses once per valve. Channels lists the valves (such as 1, 2, or DO1, DO2); empty, the one Channel. One valve gives the procedure as written.")]
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

        public IObservable<DispenseCalibration> Process(IObservable<DispenseCalibration> source)
        {
            return source.Select(settings => Expand(settings, Valves.Parse(Channels, Channel)));
        }

        /// <summary>The settings with each sample once per valve, in turn, and the priming pulses once per valve.</summary>
        public static DispenseCalibration Expand(DispenseCalibration settings, int[] valves)
        {
            var procedure = settings.Procedure;
            if (procedure == null || procedure.Samples == null || procedure.Samples.Count == 0)
            {
                throw new InvalidOperationException("The valve calibration's procedure has no samples.");
            }
            var expanded = new List<DispenseSample>();
            foreach (var sample in procedure.Samples)
            {
                foreach (var valve in valves)
                {
                    expanded.Add(new ValveSample
                    {
                        Size = sample.Size,
                        Repeats = sample.Repeats,
                        InterPulseIntervalMs = sample.InterPulseIntervalMs,
                        Channel = valve
                    });
                }
            }
            procedure.Samples = expanded;
            // ManualBalance counts the priming pulses as one burst: every valve's.
            procedure.PrimingPulses = procedure.PrimingPulses * valves.Length;
            return settings;
        }
    }

    [Combinator]
    [Description("Fires a burst of (channel, size) pulse requests, as OpenRigs.Core PulseBurst does, on the valve the sample names (an expanded procedure's sample; any other on Channel). Fed the procedure, it fires the priming burst: an equal share of the priming pulses on each valve in turn.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ValvePulseBurst
    {
        int channel = 1;

        [Description("The line a sample that names no valve fires on, 1 to 3.")]
        public int Channel
        {
            get { return channel; }
            set { channel = value; }
        }

        public IObservable<Tuple<int, int>> Process(IObservable<DispenseSample> source)
        {
            return source.SelectMany(sample =>
            {
                var valve = sample as ValveSample;
                return PulseBurst.Burst(valve != null ? valve.Channel : Channel, sample.Size, sample.Repeats, sample.InterPulseIntervalMs);
            });
        }

        public IObservable<Tuple<int, int>> Process(IObservable<DispenseProcedure> source)
        {
            return source.SelectMany(procedure =>
            {
                if (procedure.Samples == null || procedure.Samples.Count == 0)
                {
                    throw new InvalidOperationException("The dispense procedure has no samples to take the priming size from.");
                }
                var valves = Valves.Of(procedure);
                if (valves.Length == 0) valves = new[] { Channel };
                int size = procedure.PrimingSize ?? procedure.Samples.Max(sample => sample.Size);
                int interval = procedure.Samples.Max(sample => sample.InterPulseIntervalMs);
                int each = procedure.PrimingPulses / valves.Length;
                return valves.Select(valve => PulseBurst.Burst(valve, size, each, interval)).Concat();
            });
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
    }

    [Combinator]
    [Description("Each weighed burst as a row of the weights file: its pulse width in ms, its pulses, the grams before and after it, and the valve it fired on (1 to 3). Input: ((grams after, grams before), its sample), as RunCalibration gives it.")]
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

        public IObservable<ValveWeighing> Process(IObservable<Tuple<Tuple<double, double>, DispenseSample>> source)
        {
            return source.Select(input =>
            {
                var valve = input.Item2 as ValveSample;
                return new ValveWeighing
                {
                    size = input.Item2.Size,
                    repeats = input.Item2.Repeats,
                    before = input.Item1.Item2,
                    after = input.Item1.Item1,
                    channel = valve != null ? valve.Channel : Channel
                };
            });
        }
    }
}
