import os, sys, pdb
import atpy
import ephem
import numpy as np
import tutilities

G = 6.67428e-11 # gravitational constant in m^3/kg^-1/s^-2
HPLANCK = 6.62607e-34 # planck's constant in J*s
C = 2.99792e8 # speed of light in vacuum in m/s
KB = 1.3806488e-23 # boltzmann constant in J/K
RGAS = 8.314 # gas constant in J/mol/K
RSUN = 6.9551e8 # solar radius in m
RJUP = 7.1492e7 # jupiter radius in m
MJUP = 1.89852e27 # jupiter mass in kg
AU2M = 1.49598e11 # au to metres conversion factor
MUJUP = 2.22e-3 # jupiter atmosphere mean molecular weight in kg/mole
TR_TABLE = 'exoplanets_transiting.fits' # fits file for known exoplanets that transit




def emission( wav=2.2, wav_ref=2.2, obj_ref='WASP-19 b', outfile='signals_eclipses.txt', download_latest=True ):
    """
    Generates a table of properties relevant to eclipse measurements at a specified
    wavelength for all known transiting exoplanets. Basic temperature equilibrium is
    assumed, with idealised Planck blackbody spectra. Perhaps the most useful column
    of the output table is the one that gives the expected signal-to-noise of the
    eclipse **relative to the signal-to-noise for a reference planet at a reference
    wavelength**. A relative signal-to-noise is used due to the unknown normalising
    constant when working with magnitudes at arbitrary wavelengths.
    """

    # Convert the wavelengths from microns to metres:
    wav = wav / 1e6
    wav_ref = wav_ref / 1e6

    # Get table data for planets that we have enough information on:
    t = filter_table( sigtype='emission', download_latest=download_latest )
    nplanets = len( t.NAME )

    # Calculate the equilibrium temperatures for all planets on list:
    Temp_eq = Teq( t )

    # Assuming black body radiation, calculate the ratio between the
    # energy emitted by the planet per m^2 of surface per second,
    # compared to the star:
    bratio = planck( wav, Temp_eq ) / planck( wav, t.TEFF )

    # Convert the above to the ratio of the measured fluxes:
    fratio = bratio * ( ( t.R * RJUP) / ( t.RSTAR * RSUN ) )**2

    # Using the known Ks ( ~2.2microns ) magnitude as a reference,
    # approximate the magnitude in the current wavelength of interest:
    kratio = planck( wav, t.TEFF ) / planck( 2.2e-6, t.TEFF )
    mag_star = t.KS - 2.5 * np.log10( kratio )
    # Note that this assumes the magnitude of the reference star that
    # the magnitudes such as t.KS are defined wrt is approximately the
    # same at wav and 2.2 microns.

    # Convert the approximate magnitude to an unnormalised stellar flux 
    # in the wavelength of interest:
    flux_star_unnorm = 10**( -mag_star / 2.5 )

    # Use the fact that the signal-to-noise is:
    #   signal:noise = f_planet / sqrt( flux_star )
    #                = sqrt( f_star ) * fratio
    # but note that we still have the normalising
    # constant to be taken care of (see next):
    snr_unnorm = np.sqrt( flux_star_unnorm ) * fratio

    # The signal-to-noise ratio is still not normalised, so we need to repeat
    # the above for another reference star; seeing as the normalising constant
    # It might be useful to put the signal-to-noise in different units, namely,
    # compare the size of the current signal to that of another reference target 
    # at some reference wavelength. Basically repeat the above for the reference:
    ii = ( t.NAME==obj_ref )
    bratio_ref = planck( wav_ref, Temp_eq[ii] ) / planck( wav_ref, t.TEFF[ii] )
    fratio_ref = bratio_ref * ( ( t.R[ii] * RJUP ) / ( t.RSTAR[ii] * RSUN ) )**2
    kratio_ref = planck( wav_ref, t.TEFF[ii] ) / planck( 2.2e-6, t.TEFF[ii] )
    mag_ref = t.KS[ii] - 2.5 * np.log10( kratio_ref )
    flux_ref = 10**( -mag_ref/2.5 )
    snr_ref = np.sqrt( flux_ref ) * fratio_ref

    # Reexpress the signal-to-noise of our target as a scaling of the reference
    # signal-to-noise:
    snr_norm = snr_unnorm / snr_ref

    # Rearrange the targets in order of the most promising:
    s = np.argsort( snr_norm )
    s = s[::-1]

    # Open the output file and write the column headings:
    ofile = open( outfile, 'w' )
    header = make_header_ec( nplanets, wav, wav_ref, obj_ref )
    ofile.write( header )
    
    for j in range( nplanets ):
        i = s[j]
        outstr = make_outstr_ec( j+1, t.NAME[i], t.RA[i], t.DEC[i], t.KS[i], \
                                 t.TEFF[i], t.RSTAR[i], t.R[i], t.A[i], Temp_eq[i], \
                                 fratio[i], snr_norm[i] )
        ofile.write( outstr )
    ofile.close()
    print 'Saved output in {0}'.format( outfile )
    
    return outfile

def transmission( wav_vis=0.7, wav_ir=2.2, wav_ref=2.2, obj_ref='WASP-19 b', outfile='signals_transits.txt', download_latest=True ):
    """
    
    """

    # Calculate transmission signal as the variation in flux drop
    # caused by a change in the effective planetary radius by n=1
    # atmospheric scale heights; the size of the signal scales
    # approximately linearly with the number of scale heights used,
    # making it simple to extrapolate from the output this produces:
    n = 1

    # Convert the wavelengths from microns to metres:
    wav_vis = wav_vis / 1e6
    wav_ir = wav_ir / 1e6    
    wav_ref = wav_ref / 1e6

    # Make we exclude table rows that do not contain
    # all the necessary properties:
    t = filter_table( sigtype='transmission', download_latest=download_latest )
    nplanets = len( t.NAME )

    # First check to make sure we have both a V and Ks
    # magnitude for the reference star:
    ix = ( t.NAME==obj_ref )
    if ( np.isfinite( t.KS[ix] )==False ) or ( np.isfinite( t.V[ix] )==False ):
        print '\n\nPlease select a different reference star for which we have both a V and Ks magnitude\n\n'
        return None


    # Calculate the approximate planetary equilibrium temperature:
    Temp_eq = Teq( t )

    # Calculate the gravitaional accelerations at the surface zero-level:
    MPLANET = np.zeros( nplanets )
    for i in range( nplanets ):
        try:
            MPLANET[i] = np.array( t.MASS[i], dtype=float )
        except:
            MPLANET[i] = np.array( t.MSINI[i], dtype=float )
            print t.NAME[i]
    little_g = G * MPLANET * MJUP / ( t.R * RJUP )**2

    # Calculate the atmospheric scale height in metres; note that
    # we use RGAS instead of KB because MUJUP is **per mole**:
    Hatm = RGAS * Temp_eq / MUJUP / little_g

    # Calculate the approximate change in transit depth for a
    # wavelength range where some species in the atmosphere
    # increases the opacity of the planetary limb for an additional
    # 2.5 (i.e. 5/2) scale heights:
    depth_tr = ( ( t.R * RJUP ) / ( t.RSTAR * RSUN ) )**2
    delta_tr = 2 * n * ( t.R * RJUP ) * Hatm / ( t.RSTAR * RSUN )**2

    # Using the known Ks magnitude of the target, estimate the
    # unnormalised signal-to-noise ratio of the change in transit
    # depth that we would measure in the visible and IR separately:
    bratio = planck( wav_vis, t.TEFF ) / planck( 2.2e-6, t.TEFF )
    mag = t.KS - 2.5 * np.log10( bratio )
    flux_unnorm = 10**( -mag/2.5 )
    snr_unnorm_vis = np.sqrt( flux_unnorm ) * delta_tr

    bratio = planck( wav_ir, t.TEFF ) / planck( 2.2e-6, t.TEFF )
    mag = t.KS - 2.5 * np.log10( bratio )
    flux_unnorm = 10**( -mag/2.5 )
    snr_unnorm_ir = np.sqrt( flux_unnorm ) * delta_tr

    # Repeat the above using the known V band for any that didn't
    # have known KS magnitudes:
    ixs = ( np.isfinite( t.KS )==False )
    
    bratio = planck( wav_vis, t.TEFF[ixs] ) / planck( 0.6e-6, t.TEFF[ixs] )
    mag = t.V[ixs] - 2.5 * np.log10( bratio )
    flux_unnorm = 10**( -mag/2.5 )
    snr_unnorm_vis[ixs] = np.sqrt( flux_unnorm ) * delta_tr[ixs]

    bratio = planck( wav_ir, t.TEFF[ixs] ) / planck( 2.2e-6, t.TEFF[ixs] )
    mag = t.KS[ixs] - 2.5 * np.log10( bratio )
    flux_unnorm = 10**( -mag/2.5 )
    snr_unnorm_ir[ixs] = np.sqrt( flux_unnorm ) * delta_tr[ixs]
    

    # The signal-to-noise ratio is still not normalised, so we need to repeat
    # the above for another reference star; seeing as the normalising constant
    # It might be useful to put the signal-to-noise in different units, namely,
    # compare the size of the current signal to that of another reference target 
    # at some reference wavelength. Basically repeat the above for the reference:
    ii = ( t.NAME==obj_ref )
    delta_tr_ref = 2 * n * ( t.R[ii] * RJUP) * Hatm[ii] / ( t.RSTAR[ii] * RSUN )**2
    kratio_ref = planck( wav_ref, t.TEFF[ii] ) / planck( 2.2e-6, t.TEFF[ii] )

    mag_ref_ir = t.KS[ii] - 2.5 * np.log10( kratio_ref )
    flux_ref_ir = 10**( -mag_ref_ir/2.5 )
    snr_ref_ir = np.sqrt( flux_ref_ir ) * delta_tr_ref

    mag_ref_vis = t.V[ii] - 2.5 * np.log10( kratio_ref )
    flux_ref_vis = 10**( -mag_ref_vis/2.5 )
    snr_ref_vis = np.sqrt( flux_ref_vis ) * delta_tr_ref

    # Reexpress the signal-to-noise of our target as a scaling of the reference
    # signal-to-noise:
    snr_norm_vis = snr_unnorm_vis / snr_ref_vis
    snr_norm_ir = snr_unnorm_ir / snr_ref_ir

    # Rearrange the targets in order of the most promising:
    s = np.argsort( snr_norm_vis )
    s = s[::-1]

    # Open the output file and write the column headings:
    ofile = open( outfile, 'w' )
    header = make_header_tr( nplanets, wav_vis, wav_ir, wav_ref, obj_ref, n )
    ofile.write( header )
    
    for j in range( nplanets ):
        i = s[j]
        if np.isfinite( t.V[i] ):
            v = '{0:.1f}'.format( t.V[i] )
        else:
            v = '-'
        if np.isfinite( t.KS[i] ):
            ks = '{0:.1f}'.format( t.KS[i] )
        else:
            ks = '-'
        outstr = make_outstr_tr( j+1, t.NAME[i], t.RA[i], t.DEC[i], v, ks, \
                                 t.RSTAR[i], t.R[i], Temp_eq[i], \
                                 Hatm[i], depth_tr[i], delta_tr[i], \
                                 snr_norm_vis[i], snr_norm_ir[i] )
        ofile.write( outstr )
    ofile.close()
    print 'Saved output in {0}'.format( outfile )
    
    return outfile


def filter_table( sigtype=None, download_latest=True ):
    """
    Identify entries from the containing values for all of the
    required properties.
    """

    if ( os.path.isfile( TR_TABLE )==False )+( download_latest==True ):
        tutilities.download_data()
    t = atpy.Table( TR_TABLE )
    t = t.where( np.isfinite( t.RSTAR ) ) # stellar radius
    t = t.where( np.isfinite( t.R ) ) # planetary radius
    t = t.where( np.isfinite( t.A ) ) # semimajor axis
    t = t.where( np.isfinite( t.TEFF ) ) # stellar effective temperature
    if sigtype=='emission':
        t = t.where( np.isfinite( t.KS ) ) # stellar Ks magnitude
    if sigtype=='transmission':
        t = t.where( np.isfinite( t.KS ) + np.isfinite( t.V ) ) # stellar Ks and/or V magnitude
        try:
            t = t.where( ( np.isfinite( t.MSINI ) * ( t.MSINI>0 ) + \
                           ( np.isfinite( t.MASS ) * ( t.MASS>0 ) ) ) ) # MSINI and MASS available
        except:
            t = t.where( ( np.isfinite( t.MSINI ) * ( t.MSINI>0 ) ) ) # only MSINI available

    return t

def Teq( table ):
    """
    Calculates the equilibrium temperature of the planet, assuming zero
    albedo and homogeneous circulation. Assumes filter_table() has already
    been done to ensure all necessary properties are available for the
    calculation, i.e. t.RSTAR, t.A, t.TSTAR.
    """

    Rstar = table.RSTAR * RSUN
    a = table.A * AU2M
    Tstar = table.TEFF
    Teq = np.sqrt( Rstar / 2. / a ) * Tstar

    return Teq

def planck( wav, temp ):
    """
    Evaluates the Planck function for given values of wavelength
    and temperature. Wavelength should be provided in metres and
    temperature should be provided in Kelvins.
    """
    
    term1 = 2 * HPLANCK * ( C**2. ) / ( wav**5. )
    term2 = np.exp( HPLANCK * C / KB / wav / temp ) - 1
    bbflux = term1 / term2

    return bbflux


def make_header_ec( nplanets, wav, wav_ref, obj_ref ):
    """
    Generates a header in a string format that can be written to
    the top of the eclipses output file.
    """

    col1a = 'Rank'.center( 4 )
    col1b = ' '.center( 4 )
    col2a = 'Name'.center( 15 )
    col2b = ' '.center( 15 )
    col3a = 'RA'.center( 11 )
    col3b = ' '.center( 11 )
    col4a = 'Dec'.center( 12 )
    col4b = ' '.center( 12 )
    col5a = 'K '.rjust( 5 )
    col5b = '(mag)'.rjust( 5 )
    col6a = 'Tstar'.center( 6 )
    col6b = '(K)'.center( 6 )
    col7a = 'Rstar'.center( 6 )
    col7b = '(Rsun)'.center( 6 )
    col8a = 'Rp'.center( 6 )
    col8b = '(Rjup)'.center( 6 )
    col9a = 'a'.center( 5 )
    col9b = '(AU)'.center( 5 )
    col10a = 'Tpeq'.rjust( 5 )
    col10b = '(K)'.rjust( 5 )
    col11a = 'Fp/Fs'.rjust( 6 )
    col11b = '(1e-4)'.rjust( 6 )
    col12a = 'S/N'.rjust( 6 )
    col12b = ' '.rjust( 6 )
    colheadingsa = '# {0}{1} {2} {3} {4} {5} {6} {7} {8} {9} {10} {11}\n'\
                  .format( col1a, col2a, col3a, col4a, col5a, col6a, \
                          col7a, col8a, col9a, col10a, col11a, col12a )
    colheadingsb = '# {0}{1} {2} {3} {4} {5} {6} {7} {8} {9} {10} {11}\n'\
                  .format( col1b, col2b, col3b, col4b, col5b, col6b, \
                          col7b, col8b, col9b, col10b, col11b, col12b )
    nchar = max( [ len( colheadingsa ), len( colheadingsb ) ] )

    header  = '{0}\n'.format( '#'*nchar )
    header += '# Eclipse estimates at {0:.2f} micron arranged in order of increasing\n'.format( (1e6)*wav )
    header += '# detectability for {0:d} known transiting exoplanets\n#\n'.format( nplanets )
    header += '# Values for \'K\', \'Tstar\', \'Rstar\', \'Rp\', \'a\' are taken from the literature \n#\n'
    header += '# Other quantities are derived as follows:\n#\n'
    header += '#  \'Tpeq\' is the equilibrium effective temperature of the planet assuming \n'
    header += '#    absorption of all incident star light and uniform redistribution\n'
    header += '#       --->  Tpeq = np.sqrt( Rstar / 2. / a ) * Tstar \n#\n'
    header += '#  \'Fp/Fs\' is the ratio of the planetary dayside flux to the stellar flux\n'
    header += '#       --->  Fp/Fs = ( P(Tplanet)/P(Tstar) ) * ( Rplanet / Rstar )**2 \n'
    header += '#                 where P is the Planck function\n#\n'
    header += '#  \'S/N\' is the signal-to-noise estimated using the known stellar brightness\n'
    header += '#    and expressed relative to the S/N expected for {0} at {1:.2f} micron\n'.format( obj_ref, (1e6)*wav_ref )
    header += '#       --->  S/N_ref = Fp_ref / sqrt( Fs_ref )\n'
    header += '#       --->  S/N_targ = Fp / sqrt( Fs ) \n'
    header += '#       --->  S/N = S/N_target / S/N_ref\n#\n'
    header += '{0}\n#\n'.format( '#'*nchar )
    header += colheadingsa
    header += colheadingsb
    header += '{0}{1}\n'.format( '#', '-'*( nchar-1 ) )

    return header
    

def make_header_tr( nplanets, wav_vis, wav_ir, wav_ref, obj_ref, n ):
    """
    Generates a header in a string format that can be written to
    the top of the transits output file.
    """

    col1a = 'Rank'.center( 4 )
    col1b = ''.center( 4 )
    col2a = 'Name'.center( 15 )
    col2b = ''.center( 15 )
    col3a = 'RA'.center( 11 )
    col3b = ''.center( 11 )
    col4a = '  Dec'.center( 12 )
    col4b = ''.center( 12 )
    col5a = 'V '.rjust( 5 )
    col5b = '(mag)'.rjust( 5 )
    col6a = 'K '.rjust( 5 )
    col6b = '(mag)'.center( 5 )
    col7a = 'Rstar'.center( 6 )
    col7b = '(Rsun)'.center( 6 )
    col8a = 'Rp'.center( 6 )
    col8b = '(Rjup)'.center( 6 )
    col9a = 'Tpeq'.rjust( 5 )
    col9b = '(K)'.rjust( 5 )
    col10a = 'H '.rjust( 5 )
    col10b = '(km)'.rjust( 5 )
    col11a = 'Depth'.rjust( 6 )
    col11b = '(1e-2)'.rjust( 6 )
    col12a = 'Delta'.rjust( 6 )
    col12b = '(1e-4)'.rjust( 6 )
    col13a = 'S/N '.rjust( 6 )
    col13b = '(vis)'.rjust( 6 )
    col14a = 'S/N '.rjust( 6 )
    col14b = '(IR)'.rjust( 6 )
    colheadingsa = '# {0}{1} {2} {3} {4} {5} {6} {7} {8} {9} {10} {11} {12} {13}\n'\
                  .format( col1a, col2a, col3a, col4a, col5a, col6a, col7a, col8a, col9a, col10a, \
                           col11a, col12a, col13a, col14a )
    colheadingsb = '# {0}{1} {2} {3} {4} {5} {6} {7} {8} {9} {10} {11} {12} {13}\n'\
                  .format( col1b, col2b, col3b, col4b, col5b, col6b, col7b, col8b, col9b, col10b, \
                           col11b, col12b, col13b, col14b )
    nchar = max( [ len( colheadingsa ), len( colheadingsb ) ] )

    header  = '{0}\n'.format( '#'*nchar )
    header += '# Transit variation estimates at visible ({0:.2f} micron) and IR  ({01:.2f} micron) wavelengths\n'\
              .format( (1e6)*wav_vis, (1e6)*wav_ir )
    header += '# arranged in order of increasing detectability in the visible wavelength for {0:d} known\n'\
              .format( nplanets )
    header += '# transiting exoplanets\n#\n'
    header += '# SNR is given relative to the approximate signal for {0} expected at {1:.2f} microns \n#\n'\
              .format( obj_ref, (1e6)*wav_ref )
    header += '# Values for \'V\', \'K\', \'Rstar\', \'Rp\' are taken from the literature. \n#\n'
    header += '# Other quantities are derived as follows:\n#\n'
    header += '#  \'Tpeq\' is the equilibrium effective temperature of the planet assuming \n'
    header += '#    absorption of all incident star light and uniform redistribution\n'
    header += '#       --->  Tpeq = np.sqrt( Rstar / 2. / a ) * Tstar \n#\n'
    header += '#  \'H\' is the approximate atmospheric scale height \n'
    header += '#       --->   H = Rgas * Teq / mu / g \n'
    header += '#                where Rgas is the gas constant, mu is the atmospheric mean \n'
    header += '#                molecular weight and g is the acceleration due to gravity \n#\n'
    header += '#  \'Depth\' is approximate transit depth\n'
    header += '#       --->   Depth = ( Rplanet / Rstar )**2 \n#\n'
    header += '#  \'Delta\' is the relative signal variation due to a change in planetary \n'
    header += '#     radius of n={0} times the atmospheric scale height \'H\'\n'.format( n )
    header += '#       --->   Delta = 2 * n * Rplanet * H / ( Rstar**2 ) \n#\n'.format( n )
    header += '#  \'S/N\' is the signal-to-noise of the transmission signal estimated using \n'
    header += '#    the known stellar brightness and expressed relative to the S/N expected \n'
    header += '#    for {0} at {1:.2f} micron\n'.format( obj_ref, (1e6)*wav_ref )
    header += '#       --->  S/N_ref = Delta_ref / sqrt( F_ref )  \n'
    header += '#       --->  S/N_targ = Delta_targ / sqrt( F_targ )  \n'
    header += '#       --->  S/N = S/N_target / S/N_ref\n#\n'
    header += '{0}\n#\n'.format( '#'*nchar )
    header += colheadingsa
    header += colheadingsb
    header += '{0}{1}\n'.format( '#', '-'*( nchar-1 ) )

    return header

    
def make_outstr_ec( rank, name, ra, dec, kmag, tstar, rstar, rp, a, tpeq, fratio, snr_norm  ):
    """
    Takes quantities that will be written to the eclipses output and formats them nicely.
    """

    name = name.replace( ' ', '' )

    # Convert the RA to hh:mm:ss.s and Dec to dd:mm:ss.s:
    ra_str = str( ephem.hours( ra ) )
    dec_str = str( ephem.degrees( dec ) )


    if ra.replace( ' ','' )=='':
        ra_str = '?'
    elif len( ra_str )==10:
        ra_str = '0{0}'.format( ra_str )

    if dec.replace( ' ','' )=='':
        dec_str = '?'
    else:
        if float( dec )>=0:
            dec_str = '+{0}'.format( dec_str )
        if len( dec_str )==10:
            dec_str = '{0}0{1}'.format( dec_str[0], dec_str[1:] )

    rank_str = '{0}'.format( rank ).rjust( 4 )
    name_str = '{0}'.format( name ).center( 15 )
    ra_str = '{0}'.format( ra_str.replace( ':', ' ' ) ).center( 11 )
    dec_str = '{0}'.format( dec_str.replace( ':', ' ' ) ).rjust( 12 )
    kmag_str = '{0:.1f}'.format( kmag ).rjust( 5 )
    tstar_str = '{0:4d}'.format( int( tstar ) ).center( 6 )
    rstar_str = '{0:.1f}'.format( rstar ).center( 6 )
    rp_str = '{0:.1f}'.format( rp ).center( 6 )
    a_str = '{0:.3f}'.format( a ).center( 5 )
    tpeq_str = '{0:4d}'.format( int( tpeq ) ).center( 5 )
    fratio_str = '{0:.2f}'.format( (1e4)*fratio ).rjust( 6 )
    snr_str = '{0:.2f}'.format( snr_norm ).rjust( 6 )
    outstr = '  {0}{1} {2} {3} {4} {5} {6} {7} {8} {9} {10} {11}\n'\
             .format( rank_str, \
                      name_str, \
                      ra_str, \
                      dec_str, \
                      kmag_str, \
                      tstar_str, \
                      rstar_str, \
                      rp_str, \
                      a_str, \
                      tpeq_str, \
                      fratio_str, \
                      snr_str )

    return outstr


def make_outstr_tr( rank, name, ra, dec, vmag, kmag, rstar, rp, tpeq, hatm, \
                    depth_tr, delta_tr, snr_norm_vis, snr_norm_ir  ):
    """
    Takes quantities that will be written to the transits output and formats them nicely.
    """

    name = name.replace( ' ', '' )

    # Convert the RA to hh:mm:ss.s and Dec to dd:mm:ss.s:
    ra_str = str( ephem.hours( ra ) )
    dec_str = str( ephem.degrees( dec ) )

    if float( dec )>=0:
        dec_str = '+{0}'.format( dec_str )

    if len( ra_str )==10:
        ra_str = '0{0}'.format( ra_str )
    if len( dec_str )==10:
        dec_str = '{0}0{1}'.format( dec_str[0], dec_str[1:] )
    
    rank_str = '{0}'.format( rank ).rjust( 4 )
    name_str = '{0}'.format( name ).center( 15 )
    ra_str = '{0}'.format( ra_str.replace( ':', ' ' ) ).center( 11 )
    dec_str = '{0}'.format( dec_str.replace( ':', ' ' ) ).rjust( 12 )
    vmag_str = '{0}'.format( vmag ).rjust( 5 )
    kmag_str = '{0}'.format( kmag ).rjust( 5 )
    rstar_str = '{0:.1f}'.format( rstar ).center( 6 )
    rp_str = '{0:.1f}'.format( rp ).center( 6 )
    tpeq_str = '{0:4d}'.format( int( tpeq ) ).center( 5 )
    hatm_str = '{0:d}'.format( int( hatm / (1e3) ) ).rjust( 5 )
    depth_tr_str = '{0:.2f}'.format( (1e2)*depth_tr ).center( 6 )
    delta_tr_str = '{0:.2f}'.format( (1e4)*delta_tr ).center( 6 )
    snr_vis_str = '{0:.2f}'.format( snr_norm_vis ).rjust( 6 )
    snr_ir_str = '{0:.2f}'.format( snr_norm_ir ).rjust( 6 )
    outstr = '  {0}{1} {2} {3} {4} {5} {6} {7} {8} {9} {10} {11} {12} {13}\n'\
             .format( rank_str, \
                      name_str, \
                      ra_str, \
                      dec_str, \
                      vmag_str, \
                      kmag_str, \
                      rstar_str, \
                      rp_str, \
                      tpeq_str, \
                      hatm_str, \
                      depth_tr_str, \
                      delta_tr_str, \
                      snr_vis_str, \
                      snr_ir_str )

    return outstr


    
