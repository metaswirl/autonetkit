"""Console script entry point for AutoNetkit"""

from autonetkit.nidb import NIDB
import autonetkit.render as render
import random
import traceback
from datetime import datetime
import os
import shutil
import time
import autonetkit.compiler as compiler
import pkg_resources
import autonetkit.log as log
import autonetkit.ank_messaging as ank_messaging
import autonetkit.config as config
import autonetkit.ank_json as ank_json

# import autonetkit.bgp_pol as bgp_pol
# raise SystemExit

# TODO: make if measure set, then not compile - or warn if both set, as
# don't want to regen topology when measuring

try:
    ANK_VERSION = pkg_resources.get_distribution("autonetkit").version
except pkg_resources.DistributionNotFound:
    ANK_VERSION = "dev"

def resource_path(relative):
    """Makes relative to package"""
    return pkg_resources.resource_filename(__name__, relative)

def file_monitor(filename):
    """Generator based function to check if a file has changed"""
    last_timestamp = os.stat(filename).st_mtime

    while True:
        timestamp = os.stat(filename).st_mtime
        if timestamp > last_timestamp:
            last_timestamp = timestamp
            yield True
        yield False


def manage_network(input_graph_string, timestamp, hosts, build_options, reload_build=False, grid = None, ssh_pub_key = None):
    """Build, compile, render network as appropriate"""
    # import build_network_simple as build_network
    import autonetkit.build_network as build_network
    if reload_build:
# remap?
        build_network = reload(build_network)

    messaging = ank_messaging.AnkMessaging()

    if build_options['build']:
        if input_graph_string:
            graph = build_network.load(input_graph_string)
        elif grid:
            graph = build_network.grid_2d(grid)

        anm = build_network.build(graph)
        if not build_options['compile']:
            # publish without nidb
            body = ank_json.dumps(anm)
            messaging.publish_compressed("www", "client", body)

    if build_options['validate']:
        import validate
        validate.validate(anm)

    if build_options['compile']:
        if build_options['archive']:
            anm.save()
        nidb = compile_network(anm, hosts, ssh_pub_key = ssh_pub_key)
        body = ank_json.dumps(anm, nidb)
        messaging.publish_compressed("www", "client", body)
        log.debug("Sent ANM to web server")
        if build_options['archive']:
            nidb.save()
        # render.remove_dirs(["rendered"])
        if build_options['render']:
            render.render(nidb)

    if not(build_options['build'] or build_options['compile']):
        # Load from last run
        import autonetkit.anm
        anm = autonetkit.anm.AbstractNetworkModel()
        anm.restore_latest()
        nidb = NIDB()
        nidb.restore_latest()
        body = ank_json.dumps(anm, nidb)
        messaging.publish_compressed("www", "client", body)

    if build_options['diff']:
        import autonetkit.diff
        nidb_diff = autonetkit.diff.nidb_diff()
        import json
        data = json.dumps(nidb_diff, cls=ank_json.AnkEncoder, indent=4)
        log.info("Wrote diff to diff.json")
        with open("diff.json", "w") as fh:  # TODO: make file specified in config
            fh.write(data)

    # Note: this clobbers command line options
    # build_options.update(settings['General']) # update in case build has updated, eg for deploy
    # build_options.update(settings['General']) # update in case build has
    # updated, eg for deploy

    if build_options['deploy']:
        deploy_network(anm, nidb, input_graph_string, hosts)

    if build_options['measure']:
        measure_network(nidb)

    log.info("Finished")


def parse_options():
    """Parse user-provided options"""
    import argparse
    usage = "autonetkit -f input.graphml"
    version = "%(prog)s " + str(ANK_VERSION)
    parser = argparse.ArgumentParser(description=usage, version=version)

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        '--file', '-f', default=None, help="Load topology from FILE")
    input_group.add_argument('--stdin', action="store_true", default=False,
                             help="Load topology from STDIN")

    # TODO: move from -f to -i for --input
    parser.add_argument('--monitor', '-m', action="store_true",
                        default=False, help="Monitor input file for changes")
    parser.add_argument('--debug', action="store_true",
                        default=False, help="Debug mode")
    parser.add_argument('--diff', action="store_true", 
                        default=False, help="Diff NIDB")
    parser.add_argument('--compile', action="store_true",
                        default=False, help="Compile")
    parser.add_argument('--build', action="store_true", default=False, help="Build")
    parser.add_argument('--render', action="store_true", default=False, help="Compile")
    parser.add_argument('--validate', action="store_true", default=False, help="Validate")
    parser.add_argument('--deploy', action="store_true",
                        default=False, help="Deploy")
    parser.add_argument('--archive', action="store_true", default=False,
                        help="Archive ANM, NIDB, and IP allocations")
    parser.add_argument('--measure', action="store_true",
                        default=False, help="Measure")
    parser.add_argument('--hosts', action="store", 
                        default="localhost", help="Choose single or list of hosts (a,b,c) defined in the configuration file")
    parser.add_argument('--ssh_key', action="store", 
                        default="system", help="Choose ssh pub key file for quicker authentication. Takes 'none', 'system' (default, from ~/.ssh/) or an absolute file path.")
    parser.add_argument('--webserver', action="store_true", 
                        default=False, help="Webserver")
    parser.add_argument('--grid', type=int, help="Webserver")
    arguments = parser.parse_args()
    return arguments

def main():
    settings = config.settings

    options = parse_options()
    log.info("AutoNetkit %s" % ANK_VERSION)

# TODO: only allow monitor mode with options.file not options.stdin

    if options.debug or settings['General']['debug']:
        # TODO: fix this
        import logging
        logger = logging.getLogger("ANK")
        logger.setLevel(logging.DEBUG)

    build_options = {
        'compile': options.compile or settings['General']['compile'],
        'render': options.render or settings['General']['render'],
        'validate': options.validate or settings['General']['validate'],
        'build': options.build or settings['General']['build'],
        'deploy': options.deploy or settings['General']['deploy'],
        'measure': options.measure or settings['General']['measure'],
        'monitor': options.monitor or settings['General']['monitor'],
        'diff': options.diff or settings['General']['diff'],
        'archive': options.archive or settings['General']['archive'],
    }


    if options.webserver:
        log.info("Webserver not yet supported, please run as seperate module")

    if options.file:
        with open(options.file, "r") as fh:
            input_string = fh.read()
        timestamp = os.stat(options.file).st_mtime
    elif options.stdin:
        import sys
        input_string = sys.stdin
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
    elif options.grid:
        input_string = ""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
        pass # don't have input file
    else:
        log.info("No input file specified. Exiting")
        raise SystemExit

    if options.ssh_key.lower() == "system":
        home_ssh_dir = os.path.join(os.getenv("USERPROFILE") or os.getenv("HOME"), ".ssh/")
        home_ssh_file = os.path.join(home_ssh_dir, "id_dsa.pub")
        if os.path.isfile(home_ssh_file):
            log.info("Taking ssh pub key from %s" % home_ssh_file)
            with open(home_ssh_file, "rb") as f:
                ssh_pub = f.read().strip()
        home_ssh_file = os.path.join(home_ssh_dir, "id_rsa.pub")
        if os.path.isfile(home_ssh_file):
            log.info("Taking ssh pub key from %s" % home_ssh_file)
            with open(home_ssh_file, "rb") as f:
                ssh_pub = f.read().strip()
    elif options.ssh_key.lower() == "none":
        ssh_pub = None # just for the case there is a file called "false"
    elif os.path.isfile(options.ssh_key):
        log.info("Taking ssh pub key from %s" % options.ssh_key)
        with open(options.ssh_key, "rb") as f:
            ssh_pub = f.read().strip()
    else:
        log.warning("Illegal string for --ssh_key: \n%s" % options.ssh_key)
        ssh_pub = None

    hosts = options.hosts.lower().split(",")

    manage_network(input_string, timestamp, hosts, build_options=build_options, grid = options.grid, ssh_pub_key = ssh_pub )


# TODO: work out why build_options is being clobbered for monitor mode
    build_options['monitor'] = options.monitor or settings['General'][
        'monitor']

    if build_options['monitor']:
        try:
            log.info("Monitoring for updates...")
            input_filemonitor = file_monitor(options.file)
            source = resource_path("build_network.py")
            build_filemonitor = file_monitor(source)
            while True:
                time.sleep(1)
                rebuild = False
                reload_build = False
                if input_filemonitor.next():
                    rebuild = True
                if build_filemonitor.next():
                    reload_build = True
                    rebuild = True

                if rebuild:
                    try:
                        log.info("Input graph updated, recompiling network")
                        with open(options.file, "r") as fh:
                            input_string = fh.read()  # read updates
                        manage_network(input_string,
                                       timestamp, hosts, build_options, reload_build)
                        log.info("Monitoring for updates...")
                    except Exception, e:
                        log.warning("Unable to build network %s" %e)
                        traceback.print_exc()

        except KeyboardInterrupt:
            # TODO: need to close filehandles for input and output
            log.info("Exiting")


def compile_network(anm, hosts, ssh_pub_key = None ):
    nidb = NIDB()
    g_phy = anm['phy']
    g_ip = anm['ip']
    g_graphics = anm['graphics']
# TODO: build this on a platform by platform basis
    nidb.add_nodes_from(
        g_phy, retain=['label', 'host', 'platform', 'Network', 'update'])

    cd_nodes = [n for n in g_ip.nodes(
        "collision_domain") if not n.is_switch]  # Only add created cds - otherwise overwrite host of switched
    nidb.add_nodes_from(
        cd_nodes, retain=['label', 'host'], collision_domain=True)
# add edges to switches
    edges_to_add = [edge for edge in g_phy.edges()
            if edge.src.is_switch or edge.dst.is_switch]
    edges_to_add += [edge for edge in g_ip.edges() if edge.split] # cd edges from split
    nidb.add_edges_from(edges_to_add, retain='edge_id')

# TODO: boundaries is still a work in progress...
    nidb.copy_graphics(g_graphics)

    for target in hosts:
        try:
            target_data = config.settings['Hosts'][target]
        except KeyError:
            log.warning("Host %s not defined in configuration" % target)
            continue

        try:
            platform = target_data['platform']
        except KeyError:
            log.warning("no platform defined for %s" % target)
            continue
        shutil.rmtree(os.path.join("rendered", "%s_%s" % (target, platform)), ignore_errors=True)

        if platform == "netkit":
            platform_compiler = compiler.NetkitCompiler(nidb, anm, target, ssh_pub_key = ssh_pub_key)
        elif platform == "cisco":
            platform_compiler = compiler.CiscoCompiler(nidb, anm, target)
        elif platform == "dynagen":
            platform_compiler = compiler.DynagenCompiler(nidb, anm, target)
        elif platform == "junosphere":
            platform_compiler = compiler.JunosphereCompiler(nidb, anm, target)

        platform_compiler.compile()
        #if any(g_phy.nodes(host=target, platform=platform)): # this is really problematic
        #    log.info("Compile for %s on %s" % (platform, target))
        #    platform_compiler.compile()  # only compile if host set
        #else:
        #    log.debug("No devices set for %s on %s" % (platform, target))

    return nidb


def deploy_network(anm, nidb, input_graph_string, hosts):

    # TODO: make this driven from config file
    log.info("Deploying network")

    for target in hosts:
        try:
            target_data = config.settings['Hosts'][target]
        except KeyError:
            log.warning("Host %s not defined in configuration" % target)
            continue

        try:
            platform = target_data['platform']
        except KeyError:
            log.warning("no platform defined for %s" % target)
            continue

        config_path = os.path.join("rendered", "%s_%s" % (target, platform))
        
        if not target == "localhost":
            try:
                host = target_data['host']
            except KeyError:
                log.warning("Host %s has no address" % target)

            try: 
                username = target_data['username'] or ""
            except KeyError:
                username = ""
                
            try:
                key_file = target_data['keyfile'] or ""
                passwd = None 
            except KeyError:
                import getpass
                print "Please provide your password for the host", host
                passwd = getpass.getpass()
                key_file = None 

        if host == "internal":
            try:
                from autonetkit_cisco import deploy as cisco_deploy
            except ImportError:
                pass  # development module, may not be available
            if platform == "cisco":
                if input_graph_string: # input xml file
                    cisco_deploy.package(nidb, config_path, input_graph_string)
                else:
                    cisco_deploy.create_xml(anm, nidb, input_graph_string)
            continue

        if platform == "netkit":
            import autonetkit.deploy.netkit as netkit_deploy
            tar_file = netkit_deploy.package(config_path, "nklab")
            netkit_deploy.transfer(host, username, tar_file, tar_file, key_filename=key_file, password=passwd)
            netkit_deploy.extract(host, username, tar_file,
                                config_path, timeout=60, key_filename=key_file, password=passwd)
        if platform == "cisco":
            cisco_deploy.package(config_path, "nklab")

def measure_network(nidb):
    import autonetkit.measure as measure
    log.info("Measuring network")
    remote_hosts = [node.tap.ip for node in nidb.nodes("is_router")]
    dest_node = random.choice([n for n in nidb.nodes("is_l3device")])
    log.info("Tracing to randomly selected node: %s" % dest_node)
    dest_ip = dest_node.interfaces[0].ipv4_address  # choose random interface on this node

    command = "traceroute -n -a -U -w 0.5 %s" % dest_ip
    measure.send(nidb, command, remote_hosts, threads = 10)
    # abort after 10 fails, proceed on any success, 0.1 second timeout (quite aggressive)
    #command = 'vtysh -c "show ip route"'
    #measure.send(nidb, command, remote_hosts, threads = 5)
    remote_hosts = [node.tap.ip for node in nidb.nodes(
        "is_router") if node.bgp.ebgp_neighbors]
    command = "cat /var/log/zebra/bgpd.log"

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
