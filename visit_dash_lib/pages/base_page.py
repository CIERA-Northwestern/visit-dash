'''This page is a template for creating a customized page with multiple panels.
This page deliberately avoids using too many functions to make it easier to
understand how to use streamlit.
'''
# Computation imports
import copy
import importlib
import os
import types

import streamlit as st
import pandas as pd

from .. import dash_builder, utils

importlib.reload(dash_builder)


def main(config_fp: str, user_utils: types.ModuleType = None):
    '''This is the main function that runs the dashboard.

    Args:
        config_fp: The filepath to the configuration file.
        user_utils: The module containing the user-defined functions.
            Defaults to those in root_dash_lib.
    '''

    pd.options.mode.copy_on_write = True
    # This must be the first streamlit command
    st.set_page_config(layout='wide')

    # Get the builder used to construct the dashboard
    builder = dash_builder.DashBuilder(config_fp, user_utils=user_utils)

    # Set the title that shows up at the top of the dashboard
    st.title(builder.config.get('page_title','Dashboard'))
    
    # Prep data
    data, config = builder.prep_data(builder.config)
    builder.config.update(config)

    st.sidebar.markdown('# Settings Upload')
    combined_settings = builder.settings.upload_button(st.sidebar)

    # Global settings
    #st.sidebar.markdown('# Data Settings')
    setting_check = builder.interface.request_data_settings(st.sidebar)

    st.sidebar.markdown('# View Settings')
    builder.interface.request_view_settings(st.sidebar)

    # got rid of the data recategorization function
    # because it doesnt really match our goals for this dataset
    # all the infrastructure is still there though
    # if you would like to re-add, uncomment relevant sections in
    # base_page, interface, and data_handler
    selected_settings = builder.settings.common['data']
    '''data['recategorized'] = builder.recategorize_data(
        preprocessed_df=data['preprocessed'],
        new_categories=builder.config.get('new_categories', {}),
        recategorize=selected_settings['recategorize'],
        combine_single_categories=selected_settings.get(
            'combine_single_categories',
            False
        ),
    )'''


    # bounds years by the window we defined in the view settings
    window = builder.settings.common['data']['time_window']
    #print(window)
    if window == "Legacy":
        data['preprocessed'] = data['preprocessed'][data['preprocessed']['Legacy'] == "LEGACY"]
    elif window == "Current":
        data['preprocessed'] = data['preprocessed'][data['preprocessed']['Legacy'] == "CURRENT"]
    else: 
        pass

    # for future reference, if you want to set artificial bounds for year/timescale, do it here
    min_year = data['preprocessed']['Start Date'].dt.year.min()
    max_year = data['preprocessed']['Start Date'].dt.year.max()
    
    
   
    # Data axes
    # entered search category passed down to filter settings for further specification
    st.subheader('Data Axes')
    
    st.text("Note: entries from before Jan 1st, 2014 are classified as LEGACY for the purposes of data categorization")
    st.text("LEGACY classification carries different connotations... TO ASK ABOUT")

    axes_object = builder.interface.request_data_axes(st, max_year, min_year)
    if axes_object['groupby_column'] == 'Origin (International/Domestic)':
        builder.settings.common['data']['groupby_column'] = 'International'
    
    # filters data as per specs
    builder.interface.process_filter_settings(
        st,
        data['preprocessed'],
        value=builder.settings.get_settings(common_to_include=['data'])['groupby_column'],
    )

    # Apply data filters
    data['selected'] = builder.filter_data(
        data['preprocessed'],
        builder.settings.common['filters'],
    )
    
    ## this is a fun tool that will help us later
    # its to improve performance dont worry about it
    defragment = False
    if axes_object['groupby_column'] == "Visitor Institution:All":
        defragment = True

    if 'Visitor Institution:' in axes_object['groupby_column']:
        builder.settings.common['data']['groupby_column'] = 'Visitor Institution'
    if 'Host:' in axes_object['groupby_column']:
        builder.settings.common['data']['groupby_column']= 'Host'
    
    
    # filters data by year bounds selected (so that only entries which fall into this year-bound are displayed)
    reverse_month_dict = {1:'January', 2:'February', 3:'March', 4:'April', 5:'May',6:'June', 7:'July', 8:'August', 9:'September', 10:'October', 11:'November', 12:'December'}
    if (axes_object['x_column_ind'] == 0):


        # extracts time information from axes_object
        time_object = axes_object['x_column'].split(':')
        month_start = int(time_object[1])
        year_start = int(time_object[2])
        year_end = int(time_object[3])
        years_to_display = list(range(year_start+1, year_end+1))

        month_redef = [x if x<=12 else x-12 for x in range(month_start, 12+month_start)]


        data['selected']['Reindexed Year'] = utils.get_year(
                data['selected']['Start Date'], "{} 1".format(reverse_month_dict[month_start])
            )
        data['time_adjusted'] = data['selected'][data['selected']['Reindexed Year'] == year_start]

        if len(years_to_display) != 0:
            for i in years_to_display:
                temp = data['selected'][data['selected']['Reindexed Year'] == i]
                data['time_adjusted'] = pd.concat([data['time_adjusted'], temp])

            builder.settings.common['data']['x_column'] = 'Reindexed Year'
        if len(years_to_display) == 0:

            # For Fiscal Month visualizations
            def month_fisc_converter(month:int, forward=True):
                return month_redef.index(month)+1

            data['time_adjusted'].loc.__setitem__((slice(None), 'Reindexed Month'), data['time_adjusted'].__getitem__('Start Date').dt.month.map(month_fisc_converter))
            builder.settings.common['data']['x_column'] = 'Reindexed Month'
    else:
        data['time_adjusted'] = data['selected']
        builder.settings.common['data']['x_column'] = 'Calendar Year'

   

    # Aggregate data
    data['totals'] = builder.aggregate(
        data['time_adjusted'],
        builder.settings.common['data']['x_column'],
        builder.settings.common['data']['y_column'],
        aggregation_method=builder.settings.common['data']['aggregation_method'],
    )
     # Aggregate data
     
    data['aggregated'] = builder.aggregate(
            data['time_adjusted'],
            builder.settings.common['data']['x_column'],
            builder.settings.common['data']['y_column'],
            builder.settings.common['data']['groupby_column'],
            builder.settings.common['data']['aggregation_method'],
    )
    ### WORKING ON IT
    
    #print(builder.settings.common['data'])
    temp = data['aggregated'].sum()
    data['total_by_instance'] = pd.DataFrame(index = temp.index, data={'Aggregate': temp.values})
    data['total_by_instance'].sort_values(ascending=False, by='Aggregate', inplace=True)
    
    ### adds all years for which we have data back into aggregated dataframe (even if all zero that time bin);
    # more accurately displays trends across multiple years
    years_to_display.insert(0, year_start)

    # If you are going to change the configs for x_columns, make sure they are reflected below!
    if len(list(data['aggregated'].columns)) != 0:
        data['aggregated'] = data['aggregated'].T
        data['totals'] = data['totals'].T

        if builder.settings.common['data']['x_column'] == 'Reindexed Month':
            for month in month_redef:
                if month not in data['aggregated'].columns:
                    data['aggregated'].insert(month-1, month, [0 for i in range(len(data['aggregated'].index))])
                    data['totals'].insert(month-1, month, [0 for i in range(len(data['totals'].index))])
        elif builder.settings.common['data']['x_column'] == 'Reindexed Year':
            for years in years_to_display:
                if years not in data['aggregated'].columns:
                    data['aggregated'].insert(years-min(years_to_display), years, [0 for i in range(len(data['aggregated'].index))])
                    data['totals'].insert(years-min(years_to_display), years, [0 for i in range(len(data['totals'].index))])

        data['aggregated'] = data['aggregated'].T
        data['totals'] = data['totals'].T
    
    # adds NaN values to dataframe for viewing
    if not defragment:
        if 'categorical' in builder.settings.common['filters']:
            for topic in builder.settings.common['filters']['categorical'][builder.settings.get_settings(common_to_include=['data'])['groupby_column']]:
                if topic not in data['aggregated'].columns:
                    data['aggregated'][topic] = [0 for i in range(len(data['aggregated'].index))]

        

        # little subroutine to default cumulative to true when viewing visitor institutions or hosts
        if ((builder.settings.get_settings(common_to_include=['data'])['groupby_column'] == "Visitor Institution") or
        (builder.settings.get_settings(common_to_include=['data'])['groupby_column'] == "Host")):
            builder.settings.common['data']['cumulative'] = True
            

    
    print(builder.settings.common['data'])

    st.header('Data Plotting')
    st.text("Note: data entries may correspond to multiple categories, and so be represented in each grouping")
    st.text("please be cognizant of this; an accurate count of all entries is provided by 'total' option in data settings")


    # Lineplot IF data option is total or none
    data_option = builder.settings.common['data']['data_options']
    if data_option != "Year Aggregate":
        local_key = 'lineplot'
        st.subheader('Line Plot Visualization')        
        with st.expander('Lineplot settings'):
            local_opt_keys, common_opt_keys, unset_opt_keys = builder.settings.get_local_global_and_unset(
                function=builder.data_viewer.lineplot,
            )
            builder.interface.request_view_settings(
                    st,
                    ask_for=unset_opt_keys,
                    local_key=local_key,
                    selected_settings=builder.settings.local.setdefault('lineplot', {}),
                    tag=local_key,
                    default_x=builder.settings.common['data']['x_column'],
                    default_y=builder.settings.common['data']['y_column'],
            )
            local_opt_keys, common_opt_keys, unset_opt_keys = builder.settings.get_local_global_and_unset(
                function = builder.data_viewer.lineplot,
                local_key=local_key,
            )

    #constructs line plot based on specifications provided
        if data_option == "No Total":
            builder.data_viewer.lineplot(
                    df = data['aggregated'],
                    month_reindex = month_redef if builder.settings.common['data']['x_column_ind'] == 0 else None, 
                    year_reindex=years_to_display,
                    **builder.settings.get_settings(local_key)
                )
        elif data_option == "Only Total":
            builder.data_viewer.lineplot(
                df = data['totals'],
                month_reindex = month_redef if builder.settings.common['data']['x_column_ind'] == 0 else None, 
                year_reindex=years_to_display,
                **builder.settings.get_settings(local_key)
            )
        elif data_option == "Standard":
            builder.data_viewer.lineplot(
                df = data['aggregated'],
                month_reindex = month_redef if builder.settings.common['data']['x_column_ind'] == 0 else None, 
                year_reindex = years_to_display,
                totals = data['totals'],
                **builder.settings.get_settings(local_key)
            )
    # Bar Plot IF data option is aggregated
    elif data_option == "Year Aggregate":
        print(data['total_by_instance'].columns)
        st.subheader('Bar Plot Visualization')
        builder.data_viewer.barplot(
            data['total_by_instance'],
        )
        

    # View the data directly
    builder.data_viewer.write(data)

    # Settings download button
    st.sidebar.markdown('# Settings Download')
    builder.settings.download_button(st.sidebar)